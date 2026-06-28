"use client";

import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import {
  AirplaneTilt,
  ArrowUp,
  BookOpenText,
  Brain,
  CalendarBlank,
  ChatCircleText,
  Eye,
  Microphone,
  MoonStars,
  NotePencil,
  PersonSimpleSwim,
  Sparkle,
  X,
  type IconProps,
} from "@phosphor-icons/react";
import styles from "./nidra.module.css";

type ThreadId = "review" | "japan" | "reading" | "priya" | "family";
type Mode = "now" | "sleep" | "self" | "talk";

interface Thread {
  id: ThreadId;
  label: string;
  title: string;
  whisper: string;
  thought: string;
  offer: string;
  primary: string;
  secondary: string;
  icon: React.ComponentType<IconProps>;
  color: string;
  x: string;
  y: string;
  evidence: string[];
  draft?: string;
}

const threads: Thread[] = [
  {
    id: "review",
    label: "Review",
    title: "Thursday's architecture review",
    whisper: "This is the sharp edge of the week.",
    thought:
      "I would protect this before anything else. The useful move is a simple review spine, then a quieter calendar around it.",
    offer:
      "I can pull your notes into a 12 minute flow and keep Thursday afternoon from getting chipped away.",
    primary: "Make the spine",
    secondary: "Hold Thursday",
    icon: CalendarBlank,
    color: "#ef8068",
    x: "58%",
    y: "39%",
    evidence: [
      "You searched ownership boundaries twice.",
      "The design doc stayed open after dinner.",
      "The invite has three senior reviewers.",
    ],
  },
  {
    id: "japan",
    label: "Japan",
    title: "Spring Japan trip",
    whisper: "This wants to stay gentle.",
    thought:
      "I think you want Kyoto to slow the trip down, not optimize it. Walkable, quiet, and a little textured feels more like you.",
    offer:
      "I can shape Tokyo and Kyoto into a loose route with two open afternoons.",
    primary: "Shape the route",
    secondary: "Save the ryokan",
    icon: AirplaneTilt,
    color: "#8ac9a6",
    x: "30%",
    y: "40%",
    evidence: [
      "You lingered on rail maps and ryokan pages.",
      "You kept avoiding hotel chains.",
      "Your spring calendar has a clean opening.",
    ],
  },
  {
    id: "reading",
    label: "Reading",
    title: "Consensus reading",
    whisper: "You are hunting for language.",
    thought:
      "This is not just background reading. You are collecting a clearer way to explain tradeoffs when the room gets abstract.",
    offer:
      "I found one paper worth reading slowly and one explainer worth skipping.",
    primary: "Queue the paper",
    secondary: "Make a brief",
    icon: BookOpenText,
    color: "#91a9ea",
    x: "76%",
    y: "51%",
    evidence: [
      "Raft notes sat beside the review doc.",
      "You focused on failure modes.",
      "You bounced between papers and implementation posts.",
    ],
  },
  {
    id: "priya",
    label: "Priya",
    title: "Priya reply",
    whisper: "I can keep this small.",
    thought:
      "You owe Priya a reply, and it should not become a writing task. I drafted it in your shorter tone.",
    offer: "It is casual, specific, and still unsent.",
    primary: "Review the draft",
    secondary: "Remind later",
    icon: ChatCircleText,
    color: "#dc8aaa",
    x: "24%",
    y: "62%",
    evidence: [
      "Her message sat unread after the doc push.",
      "You usually answer her fastest.",
      "Your recent replies skip greetings and sign-offs.",
    ],
    draft:
      "yeah, this makes sense. I want to tighten the ownership bit before the review, but the shape is right. I can send a pass tonight.",
  },
  {
    id: "family",
    label: "Swim",
    title: "Kid activities",
    whisper: "A small window is opening.",
    thought:
      "From recent photos, this seems like a good moment to try swimming or a weekend sport before spring signups get loud.",
    offer:
      "I can find three nearby options and keep it practical, not aspirational.",
    primary: "Find options",
    secondary: "Ask this weekend",
    icon: PersonSimpleSwim,
    color: "#77c7d1",
    x: "62%",
    y: "67%",
    evidence: [
      "Pool photos showed up more than once.",
      "Weekend mornings look less crowded.",
      "Nearby programs are opening spring lists.",
    ],
  },
];

const selfLines = [
  {
    icon: Brain,
    title: "I protect your mornings.",
    body: "When the work is architectural, an unbroken morning matters more than a tidy calendar.",
  },
  {
    icon: NotePencil,
    title: "I draft in your voice.",
    body: "Short. Specific. Warm only where warmth is useful.",
  },
  {
    icon: Eye,
    title: "I notice patterns across surfaces.",
    body: "Reading, search, calendar, messages, and photos become one lived picture, with your approval before action.",
  },
];

const sleepLines = [
  {
    icon: CalendarBlank,
    title: "I changed one belief.",
    body: "It is not just that you dislike meetings. You need mornings protected when the work shapes architecture.",
  },
  {
    icon: AirplaneTilt,
    title: "I softened the Japan plan.",
    body: "The right trip is not packed. It has quiet Kyoto time and a route that can breathe.",
  },
  {
    icon: BookOpenText,
    title: "I connected the reading.",
    body: "Consensus papers are feeding Thursday's review language, especially around failure modes.",
  },
  {
    icon: PersonSimpleSwim,
    title: "I kept family in view.",
    body: "Swimming looks timely, but I will keep it to a few useful options.",
  },
];

export default function NidraMockPage() {
  const [mode, setMode] = useState<Mode>("now");
  const [selectedId, setSelectedId] = useState<ThreadId>("review");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [toast, setToast] = useState("");

  const selected = useMemo(
    () => threads.find((thread) => thread.id === selectedId) ?? threads[0],
    [selectedId],
  );

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const params = new URLSearchParams(window.location.search);
      const requestedMode = params.get("mode") ?? params.get("surface");
      const requestedThread = params.get("thread");

      if (isMode(requestedMode)) {
        setMode(
          requestedMode === "home"
            ? "now"
            : requestedMode === "you"
              ? "self"
              : requestedMode,
        );
      }

      if (isThreadId(requestedThread)) {
        setSelectedId(requestedThread);
        setSheetOpen(true);
      }
    });

    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!toast) {
      return;
    }
    const timeout = window.setTimeout(() => setToast(""), 2500);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  function openThread(id: ThreadId) {
    setSelectedId(id);
    setSheetOpen(true);
  }

  function approve(label: string) {
    setToast(`I prepared "${label}" and kept it waiting for approval.`);
    setSheetOpen(false);
  }

  return (
    <main className={styles.page}>
      <section className={styles.stage} aria-label="Nidra iOS companion mock">
        <div className={styles.phone}>
          <Image
            src="/nidra/memory-field.png"
            alt=""
            fill
            priority
            sizes="430px"
            className={styles.memoryImage}
          />
          <div className={styles.veil} />
          <StatusBar />

          <div className={styles.island} aria-hidden="true" />

          {mode === "now" ? (
            <header className={styles.topRail}>
              <button type="button" onClick={() => setMode("self")}>
                <Brain size={20} weight="duotone" aria-hidden="true" />
                <span>You</span>
              </button>
              <div className={styles.brandPill}>Nidra</div>
              <button type="button" onClick={() => setMode("sleep")}>
                <MoonStars size={20} weight="duotone" aria-hidden="true" />
                <span>Sleep</span>
              </button>
            </header>
          ) : null}

          <section
            className={`${styles.mode} ${mode === "now" ? styles.modeActive : ""}`}
            aria-hidden={mode !== "now"}
          >
            <NowView
              threads={threads}
              onThread={openThread}
              onTalk={() => setMode("talk")}
            />
          </section>

          <section
            className={`${styles.mode} ${mode === "self" ? styles.modeActive : ""}`}
            aria-hidden={mode !== "self"}
          >
            <SelfView onClose={() => setMode("now")} />
          </section>

          <section
            className={`${styles.mode} ${mode === "sleep" ? styles.modeActive : ""}`}
            aria-hidden={mode !== "sleep"}
          >
            <SleepView
              onClose={() => setMode("now")}
              onStart={() => openThread("review")}
            />
          </section>

          <section
            className={`${styles.mode} ${mode === "talk" ? styles.modeActive : ""}`}
            aria-hidden={mode !== "talk"}
          >
            <TalkView
              onClose={() => setMode("now")}
              onPriya={() => openThread("priya")}
            />
          </section>

          <ThreadSheet
            open={sheetOpen}
            thread={selected}
            onClose={() => setSheetOpen(false)}
            onApprove={approve}
          />

          {toast ? <div className={styles.toast}>{toast}</div> : null}
          <div className={styles.homeIndicator} aria-hidden="true" />
        </div>
      </section>
    </main>
  );
}

function NowView({
  threads,
  onThread,
  onTalk,
}: {
  threads: Thread[];
  onThread: (id: ThreadId) => void;
  onTalk: () => void;
}) {
  return (
    <div className={styles.now}>
      <div className={styles.letter}>
        <p>I woke up with one thing in my hands.</p>
        <h1>Thursday is the thing to protect.</h1>
        <span>
          I can make the week feel less sharp: start with the review, keep Japan
          soft, answer Priya, and find one swim option.
        </span>
      </div>

      <div className={styles.memoryLens} aria-hidden="true">
        <span className={styles.lensHalo} />
        <span className={styles.lensCore} />
      </div>

      <div className={styles.threadField} aria-label="Things Nidra is holding">
        <span className={`${styles.strand} ${styles.strandReview}`} />
        <span className={`${styles.strand} ${styles.strandJapan}`} />
        <span className={`${styles.strand} ${styles.strandReading}`} />
        <span className={`${styles.strand} ${styles.strandPriya}`} />
        <span className={`${styles.strand} ${styles.strandFamily}`} />
        {threads.map((thread) => (
          <button
            key={thread.id}
            type="button"
            className={styles.threadBead}
            style={
              {
                "--thread-color": thread.color,
                "--x": thread.x,
                "--y": thread.y,
              } as React.CSSProperties
            }
            onClick={() => onThread(thread.id)}
          >
            <thread.icon size={21} weight="duotone" aria-hidden="true" />
            <span>{thread.label}</span>
          </button>
        ))}
      </div>

      <div className={styles.currentThought}>
        <button type="button" onClick={() => onThread("review")}>
          <span>Start there</span>
          <ArrowUp size={17} weight="bold" aria-hidden="true" />
        </button>
        <button type="button" onClick={onTalk}>
          <Microphone size={18} weight="duotone" aria-hidden="true" />
          <span>Talk to me</span>
        </button>
      </div>
    </div>
  );
}

function SelfView({ onClose }: { onClose: () => void }) {
  return (
    <div className={styles.overlayMode}>
      <CloseButton onClick={onClose} label="Close self view" />
      <div className={styles.modeIntro}>
        <Brain size={38} weight="duotone" aria-hidden="true" />
        <p>How I understand you</p>
        <h1>I am learning the shape of your life, not just storing facts.</h1>
      </div>

      <div className={styles.lineList}>
        {selfLines.map((line) => (
          <article key={line.title} className={styles.lifeLine}>
            <line.icon size={22} weight="duotone" aria-hidden="true" />
            <div>
              <h2>{line.title}</h2>
              <p>{line.body}</p>
            </div>
          </article>
        ))}
      </div>

      <button className={styles.returnButton} type="button" onClick={onClose}>
        Back to now
      </button>
    </div>
  );
}

function SleepView({
  onClose,
  onStart,
}: {
  onClose: () => void;
  onStart: () => void;
}) {
  return (
    <div className={styles.overlayMode}>
      <CloseButton onClick={onClose} label="Close sleep view" />
      <div className={styles.modeIntro}>
        <MoonStars size={38} weight="duotone" aria-hidden="true" />
        <p>While you slept</p>
        <h1>I replayed the day and changed my mind a little.</h1>
        <span>
          I used to think you wanted fewer meetings. Now I think mornings need
          protection when the work is architectural.
        </span>
      </div>

      <div className={styles.lineList}>
        {sleepLines.map((line) => (
          <article key={line.title} className={styles.lifeLine}>
            <line.icon size={22} weight="duotone" aria-hidden="true" />
            <div>
              <h2>{line.title}</h2>
              <p>{line.body}</p>
            </div>
          </article>
        ))}
      </div>

      <button className={styles.returnButton} type="button" onClick={onStart}>
        Start with Thursday
      </button>
    </div>
  );
}

function TalkView({
  onClose,
  onPriya,
}: {
  onClose: () => void;
  onPriya: () => void;
}) {
  return (
    <div className={styles.overlayMode}>
      <CloseButton onClick={onClose} label="Close talk view" />
      <div className={styles.modeIntro}>
        <ChatCircleText size={38} weight="duotone" aria-hidden="true" />
        <p>Talk to Nidra</p>
        <h1>Say it messy. I already have the context.</h1>
      </div>

      <div className={styles.bubbles}>
        <div className={styles.nidraBubble}>
          I would make Thursday smaller first. Want me to turn the review into a
          tight spine?
        </div>
        <div className={styles.meBubble}>yes, and include the consensus angle</div>
        <div className={styles.nidraBubble}>
          Done. I kept it focused on failure modes, ownership boundaries, and
          the decision you need from the room.
        </div>
        <button type="button" className={styles.inlineAction} onClick={onPriya}>
          Priya is the next small thing
        </button>
      </div>

      <div className={styles.composer}>
        <span>What should I change?</span>
        <button type="button" aria-label="Send">
          <ArrowUp size={18} weight="bold" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

function ThreadSheet({
  open,
  thread,
  onClose,
  onApprove,
}: {
  open: boolean;
  thread: Thread;
  onClose: () => void;
  onApprove: (label: string) => void;
}) {
  return (
    <div className={`${styles.sheetLayer} ${open ? styles.sheetOpen : ""}`}>
      <button
        type="button"
        className={styles.scrim}
        aria-label="Close thread"
        onClick={onClose}
      />
      <section className={styles.sheet} aria-hidden={!open}>
        <div className={styles.grip} aria-hidden="true" />
        <div className={styles.sheetHead}>
          <div
            className={styles.sheetIcon}
            style={{ "--thread-color": thread.color } as React.CSSProperties}
          >
            <thread.icon size={27} weight="duotone" aria-hidden="true" />
          </div>
          <button type="button" onClick={onClose} aria-label="Close">
            <X size={17} weight="bold" aria-hidden="true" />
          </button>
        </div>

        <p className={styles.sheetWhisper}>{thread.whisper}</p>
        <h1>{thread.title}</h1>
        <p className={styles.sheetThought}>{thread.thought}</p>

        <div className={styles.offer}>
          <Sparkle size={18} weight="fill" aria-hidden="true" />
          <p>{thread.offer}</p>
        </div>

        {thread.draft ? <blockquote>{thread.draft}</blockquote> : null}

        <div className={styles.evidence}>
          <span>What I noticed</span>
          {thread.evidence.map((item) => (
            <p key={item}>{item}</p>
          ))}
        </div>

        <div className={styles.sheetActions}>
          <button type="button" onClick={() => onApprove(thread.primary)}>
            {thread.primary}
          </button>
          <button type="button" onClick={() => onApprove(thread.secondary)}>
            {thread.secondary}
          </button>
        </div>
      </section>
    </div>
  );
}

function StatusBar() {
  return (
    <div className={styles.statusBar} aria-hidden="true">
      <span>7:02</span>
      <span className={styles.statusRight}>
        <span className={styles.signal} />
        <span className={styles.battery} />
      </span>
    </div>
  );
}

function CloseButton({
  onClick,
  label,
}: {
  onClick: () => void;
  label: string;
}) {
  return (
    <button type="button" className={styles.closeButton} onClick={onClick}>
      <X size={18} weight="bold" aria-hidden="true" />
      <span className={styles.srOnly}>{label}</span>
    </button>
  );
}

function isMode(value: string | null): value is Mode | "home" | "you" {
  return (
    value === "now" ||
    value === "home" ||
    value === "you" ||
    value === "sleep" ||
    value === "self" ||
    value === "talk"
  );
}

function isThreadId(value: string | null): value is ThreadId {
  return (
    value === "review" ||
    value === "japan" ||
    value === "reading" ||
    value === "priya" ||
    value === "family"
  );
}
