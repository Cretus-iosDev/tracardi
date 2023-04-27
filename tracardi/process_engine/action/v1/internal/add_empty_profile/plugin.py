from datetime import datetime
from uuid import uuid4
from tracardi.domain.entity import Entity
from tracardi.domain.event import EventSession
from tracardi.domain.metadata import ProfileMetadata
from tracardi.domain.profile import Profile
from tracardi.domain.session import Session, SessionMetadata, SessionTime
from tracardi.domain.time import ProfileTime, ProfileVisit
from tracardi.domain.value_object.operation import Operation
from tracardi.service.plugin.domain.register import Plugin, Spec, MetaData, Documentation, PortDoc
from tracardi.service.plugin.domain.result import Result
from tracardi.service.plugin.runner import ActionRunner


class AddEmptyProfileAction(ActionRunner):

    async def run(self, payload: dict, in_edge=None) -> Result:

        now = datetime.utcnow()
        profile = Profile(
            id=str(uuid4()),
            metadata=ProfileMetadata(
                time=ProfileTime(
                    insert=now,
                    visit=ProfileVisit(
                        count=1,
                        current=datetime.utcnow()
                    )
                )
            ),
            operation=Operation(update=True)
        )

        self.event.profile = profile
        self.event.metadata.profile_less = False
        self.event.operation.update = True

        session = Session(
            id=str(uuid4()),
            profile=Entity(id=profile.id),
            metadata=SessionMetadata(
                time=SessionTime(insert=datetime.utcnow(), timestamp=datetime.timestamp(datetime.utcnow()))),
            operation=Operation(update=True)
        )

        if self.session is not None:
            self.console.warning(f"Old session {self.session.id} was replaced by new session {session.id}. "
                                 f"Replacing session is not a good practice if you already have a session.")

        self.session = session

        self.event.session = EventSession(
            id=session.id,
            start=session.metadata.time.insert,
            duration=session.metadata.time.duration
        )

        self.execution_graph.set_sessions(session)
        self.execution_graph.set_profiles(profile)

        self.tracker_payload.session.id = session.id
        self.tracker_payload.profile_less = False
        self.tracker_payload.options.update({"saveSession": True})

        return Result(port='payload', value=payload)


def register() -> Plugin:
    return Plugin(
        start=False,
        spec=Spec(
            module=__name__,
            className='AddEmptyProfileAction',
            inputs=["payload"],
            outputs=['payload'],
            version='0.7.0',
            license="MIT",
            author="Risto Kowaczewski",
            init=None,
            form=None,

        ),
        metadata=MetaData(
            name='Create empty profile',
            desc='Ads new profile to the event. Empty profile gets created with random id.',
            icon='profile',
            keywords=['new', 'create', 'add'],
            group=["Operations"],
            documentation=Documentation(
                inputs={
                    "payload": PortDoc(desc="This port takes payload object.")
                },
                outputs={
                    "payload": PortDoc(desc="Returns input payload.")
                }
            )
        )
    )
