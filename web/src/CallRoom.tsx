import {
  BarVisualizer,
  LiveKitRoom,
  RoomAudioRenderer,
  useRoomContext,
  useTranscriptions,
  useVoiceAssistant,
} from "@livekit/components-react";
import "@livekit/components-styles";
import type { JoinInfo } from "./api";
import { speakerLabel } from "@/lib/speaker";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

export function CallRoom({
  join,
  onLeave,
}: {
  join: JoinInfo;
  onLeave: () => void;
}) {
  return (
    <LiveKitRoom
      serverUrl={join.url}
      token={join.token}
      connect
      audio
      video={false}
      onDisconnected={onLeave}
    >
      <RoomAudioRenderer />
      {join.mode === "listen" ? (
        <ListenStage room={join.room} phone={join.phone} onLeave={onLeave} />
      ) : (
        <AgentStage room={join.room} onLeave={onLeave} />
      )}
    </LiveKitRoom>
  );
}

function LeaveButton({ onLeave }: { onLeave: () => void }) {
  const roomContext = useRoomContext();
  return (
    <Button
      variant="destructive"
      size="sm"
      onClick={() => {
        roomContext.disconnect();
        onLeave();
      }}
    >
      Leave monitor
    </Button>
  );
}

function ListenStage({
  room,
  phone,
  onLeave,
}: {
  room: string;
  phone?: string;
  onLeave: () => void;
}) {
  const transcriptions = useTranscriptions();
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Monitoring</p>
          <p className="font-medium">{phone ?? room}</p>
        </div>
        <LeaveButton onLeave={onLeave} />
      </div>
      <p className="text-sm text-muted-foreground">Live transcript from the room.</p>
      <ScrollArea className="h-48 rounded-lg border p-3">
        <ol className="space-y-2 text-sm">
          {transcriptions.map((line) => (
            <li key={line.streamInfo.id}>
              <span className="mr-2 font-medium text-muted-foreground">
                {speakerLabel(
                  line.participantInfo.identity,
                  (line.participantInfo as { identity: string; name?: string }).name,
                )}
              </span>
              {line.text}
            </li>
          ))}
        </ol>
      </ScrollArea>
    </div>
  );
}

function AgentStage({ room, onLeave }: { room: string; onLeave: () => void }) {
  const { state, audioTrack } = useVoiceAssistant();
  const transcriptions = useTranscriptions();
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Live room</p>
          <p className="font-medium">{room}</p>
        </div>
        <LeaveButton onLeave={onLeave} />
      </div>
      <BarVisualizer className="h-16 w-full" state={state} trackRef={audioTrack} barCount={7} />
      <p className="text-sm text-muted-foreground">{state}</p>
      <ScrollArea className="h-48 rounded-lg border p-3">
        <ol className="space-y-2 text-sm">
          {transcriptions.map((line) => (
            <li key={line.streamInfo.id}>
              <span className="mr-2 font-medium text-muted-foreground">
                {speakerLabel(
                  line.participantInfo.identity,
                  (line.participantInfo as { identity: string; name?: string }).name,
                )}
              </span>
              {line.text}
            </li>
          ))}
        </ol>
      </ScrollArea>
    </div>
  );
}
