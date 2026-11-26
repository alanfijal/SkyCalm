"""One revocable, 24-hour family view per flight revision. The link never carries an owner ID."""

import hashlib
import hmac
import re
import secrets

from services.forecast.api import RequestError
from services.passengers.store import encode

TOKEN = re.compile(r"([0-9a-f]{32})\.([0-9a-f]{64})")


def unavailable():
    return RequestError("link_unavailable", "This flight link has expired or was removed.", 404)


def signature(grant):
    message = f"forecast-v1/{grant['selector']}/{grant['revision']}/{grant['until']}"
    return hmac.new(bytes.fromhex(grant["key"]), message.encode(), hashlib.sha256).hexdigest()


def set_link(store, flight, now, create):
    owner = flight["pk"]
    selector = flight["id"].replace("-", "")
    expires = min(now + 86400, int(flight["expiresAt"]))
    pointer = store.key("link#" + selector, "forecast")
    guard = dict(
        ConditionExpression="revision=:rev AND expiresAt>:now",
        ExpressionAttributeValues=encode({":rev": flight["revision"], ":now": now}),
    )
    update = {**store.key(owner, flight["sk"]), **guard}
    if create:
        grant = {
            "selector": selector,
            "key": secrets.token_hex(32),
            "revision": flight["revision"],
            "until": expires,
        }
        update.update(
            UpdateExpression="SET familyGrant=:grant",
            ExpressionAttributeValues={
                **update["ExpressionAttributeValues"],
                ":grant": encode({"g": grant})["g"],
            },
        )
        alias = {
            "Put": {
                "TableName": store.name,
                "Item": encode(
                    {
                        "pk": "link#" + selector,
                        "sk": "forecast",
                        "owner": owner,
                        "slot": flight["slot"],
                        "expiresAt": expires,
                    }
                ),
            }
        }
    else:
        update["UpdateExpression"] = "REMOVE familyGrant"
        alias = {"Delete": pointer}
    store.transact(owner, [{"Update": update}, alias])
    return (
        {"token": f"{selector}.{signature(grant)}", "expiresAt": expires}
        if create
        else {"revoked": True}
    )


def read_link(store, token, now):
    match = TOKEN.fullmatch(token) if isinstance(token, str) else None
    if not match:
        raise unavailable()
    selector, supplied = match.groups()
    alias = store.get("link#" + selector, "forecast")
    if alias.get("expiresAt", 0) <= now:
        raise unavailable()
    owner = alias["owner"]
    flight = store.get(owner, f"flight#{alias['slot']}")
    grant = flight.get("familyGrant") or {}
    if (
        grant.get("selector") != selector
        or grant.get("until", 0) <= now
        or grant.get("revision") != flight.get("revision")
        or flight.get("expiresAt", 0) <= now
        or not hmac.compare_digest(signature(grant), supplied)
        or store.get(owner, "account").get("erasing")
    ):
        raise unavailable()
    from services.passengers.journey import forecast_for

    return {
        "flight": {
            k: flight[k] for k in ("origin", "destination", "departure", "arrival", "watch")
        },
        "forecast": forecast_for(store, flight),
        "expiresAt": grant["until"],
    }
