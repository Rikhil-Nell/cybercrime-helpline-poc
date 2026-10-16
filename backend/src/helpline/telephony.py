import logging

from livekit import api

from helpline.settings import settings

log = logging.getLogger(__name__)

DISPATCH_NAME = "helpline-inbound"


def livekit_api() -> api.LiveKitAPI:
    return api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )


def participant_token(room: str, identity: str, *, publish: bool) -> str:
    grants = api.VideoGrants(
        room_join=True,
        room=room,
        can_publish=publish,
        can_subscribe=True,
        can_publish_data=publish,
    )
    return (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(grants)
        .to_jwt()
    )


async def ensure_inbound() -> None:
    """Inbound only: wire the Twilio number to this worker via SIP dispatch rules.

    Outbound dialing is NOT here — the worker entrypoint calls sip.create_sip_participant
    after ctx.connect() when dispatch metadata includes phone_number.
    """
    lk = livekit_api()
    try:
        listed = await lk.sip.list_inbound_trunk(api.ListSIPInboundTrunkRequest())
        trunk_id = ""
        for trunk in listed.items:
            if settings.twilio_number in list(trunk.numbers):
                trunk_id = trunk.sip_trunk_id
                break
        if not trunk_id:
            created = await lk.sip.create_inbound_trunk(
                api.CreateSIPInboundTrunkRequest(
                    trunk=api.SIPInboundTrunkInfo(
                        name="Twilio inbound",
                        numbers=[settings.twilio_number],
                    )
                )
            )
            trunk_id = created.sip_trunk_id
            log.info("created inbound trunk %s for %s", trunk_id, settings.twilio_number)

        rules = await lk.sip.list_dispatch_rule(api.ListSIPDispatchRuleRequest())
        for rule in rules.items:
            if rule.name != DISPATCH_NAME:
                continue
            if trunk_id not in list(rule.trunk_ids):
                await lk.sip.update_dispatch_rule_fields(rule.sip_dispatch_rule_id, trunk_ids=[trunk_id])
                log.info("pointed %s at trunk %s", DISPATCH_NAME, trunk_id)
            return

        await lk.sip.create_dispatch_rule(
            api.CreateSIPDispatchRuleRequest(
                dispatch_rule=api.SIPDispatchRuleInfo(
                    name=DISPATCH_NAME,
                    trunk_ids=[trunk_id],
                    rule=api.SIPDispatchRule(
                        dispatch_rule_individual=api.SIPDispatchRuleIndividual(room_prefix="call-")
                    ),
                    room_config=api.RoomConfiguration(
                        agents=[
                            api.RoomAgentDispatch(
                                agent_name=settings.agent_name,
                                metadata="{}",
                            )
                        ]
                    ),
                )
            )
        )
        log.info("created dispatch rule %s", DISPATCH_NAME)
    finally:
        await lk.aclose()
