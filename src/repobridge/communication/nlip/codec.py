"""Map RepoBridge envelopes to and from NLIP (ECMA-430) messages.

Layout of one NLIP message (see docs/communication.md for the full table):

    messagetype            = envelope kind (work_order, result, evidence_request, ...)
    format/subformat       = structured/json, label "envelope": {"schema", "kind"[, "error"]}
    submessages:
      structured/json  label "record"  one per contract record (its to_dict())
      structured/uri   label "ref"     one per reference, as ev://<percent-encoded id>
      token/conversation               the investigation ID (NLIP echoes it back)
      token/workorder  label "order"   the work-order ID (application token, echoed)
      text/english     label "intent"  optional one-line intent, for logs only

ECMA-430 field names are case-insensitive, so incoming keys are lower-cased before parsing.
"""

from typing import Any
from urllib.parse import quote, unquote

from nlip_sdk.nlip import AllowedFormats, NLIP_Message, NLIP_SubMessage, ReservedTokens

from repobridge.communication.envelope import (
    ENVELOPE_SCHEMA,
    Envelope,
    MessageKind,
    ProtocolError,
)
from repobridge.core import schemas as s
from repobridge.core.serialization import ContractError

REF_SCHEME = "ev://"
ORDER_TOKEN = "workorder"
LABEL_ENVELOPE, LABEL_RECORD, LABEL_REF, LABEL_ORDER, LABEL_INTENT = (
    "envelope",
    "record",
    "ref",
    "order",
    "intent",
)


def _same(a: str | None, b: str) -> bool:
    return a is not None and a.lower() == b.lower()


def to_nlip(env: Envelope) -> NLIP_Message:
    header: dict[str, Any] = {"schema": ENVELOPE_SCHEMA, "kind": env.kind.value}
    if env.error is not None:
        header["error"] = env.error
    msg = NLIP_Message(
        messagetype=env.kind.value,
        format=AllowedFormats.structured,
        subformat="json",
        content=header,
        label=LABEL_ENVELOPE,
    )
    subs = [
        NLIP_SubMessage(
            format=AllowedFormats.structured,
            subformat="json",
            content=r.to_dict(),
            label=LABEL_RECORD,
        )
        for r in env.records
    ]
    subs += [
        NLIP_SubMessage(
            format=AllowedFormats.structured,
            subformat="uri",
            content=REF_SCHEME + quote(r, safe=""),
            label=LABEL_REF,
        )
        for r in env.refs
    ]
    subs.append(
        NLIP_SubMessage(
            format=AllowedFormats.token,
            subformat=ReservedTokens.conv.value,
            content=env.investigation_id,
        )
    )
    if env.order_id is not None:
        subs.append(
            NLIP_SubMessage(
                format=AllowedFormats.token,
                subformat=ORDER_TOKEN,
                content=env.order_id,
                label=LABEL_ORDER,
            )
        )
    if env.intent is not None:
        subs.append(
            NLIP_SubMessage(
                format=AllowedFormats.text,
                subformat="english",
                content=env.intent,
                label=LABEL_INTENT,
            )
        )
    msg.submessages = subs
    return msg


def from_nlip(msg: NLIP_Message) -> Envelope:
    if ReservedTokens.is_control(msg.messagetype):
        raise ProtocolError("NLIP control messages are not RepoBridge envelopes")
    if not (
        _same(msg.format, "structured")
        and _same(msg.subformat, "json")
        and isinstance(msg.content, dict)
        and msg.content.get("schema") == ENVELOPE_SCHEMA
    ):
        raise ProtocolError(f"main message is not a {ENVELOPE_SCHEMA} header")
    try:
        kind = MessageKind((msg.messagetype or "").lower())
    except ValueError:
        raise ProtocolError(f"unknown messagetype {msg.messagetype!r}") from None
    if msg.content.get("kind") != kind.value:
        raise ProtocolError("messagetype and envelope header disagree")

    records, refs = [], []
    investigation = order = intent = None
    for sub in msg.submessages or []:
        fmt, sf, label = sub.format, sub.subformat, sub.label
        if _same(fmt, "structured") and _same(sf, "json") and _same(label, LABEL_RECORD):
            try:
                records.append(s.load(sub.content))
            except ContractError as exc:
                raise ProtocolError(f"bad record: {exc}") from exc
        elif _same(fmt, "structured") and _same(sf, "uri") and _same(label, LABEL_REF):
            if not isinstance(sub.content, str) or not sub.content.startswith(REF_SCHEME):
                raise ProtocolError(f"ref must be an {REF_SCHEME} URI, got {sub.content!r}")
            refs.append(unquote(sub.content[len(REF_SCHEME) :]))
        elif _same(fmt, "token") and ReservedTokens.is_conv(sf):
            investigation = sub.content
        elif _same(fmt, "token") and _same(sf, ORDER_TOKEN):
            order = sub.content
        elif _same(fmt, "text") and _same(label, LABEL_INTENT):
            intent = sub.content
        else:
            raise ProtocolError(f"unexpected submessage {fmt}/{sf} label={label!r}")
    if investigation is None:
        raise ProtocolError("missing conversation token (investigation ID)")
    return Envelope(
        kind=kind,
        investigation_id=investigation,
        order_id=order,
        records=tuple(records),
        refs=tuple(refs),
        intent=intent,
        error=msg.content.get("error"),
    )


def _lower_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k.lower(): v for k, v in obj.items()}
    return obj


def nlip_from_wire(data: dict[str, Any]) -> NLIP_Message:
    """Parse a received NLIP JSON object, accepting field names in any case (ECMA-430)."""
    data = _lower_keys(data)
    if isinstance(data.get("submessages"), list):
        data["submessages"] = [_lower_keys(sm) for sm in data["submessages"]]
    try:
        return NLIP_Message.model_validate(data)
    except ValueError as exc:  # pydantic.ValidationError subclasses ValueError
        raise ProtocolError(f"not a valid NLIP message: {exc}") from exc


def nlip_to_wire(msg: NLIP_Message) -> str:
    return msg.to_json()
