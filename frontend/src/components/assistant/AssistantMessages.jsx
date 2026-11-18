import React, { useState } from "react";
import { assistantRequest } from "../../services/api";
import { ExternalLink } from "../common";

// Text remains escaped by React; never inject model-provided HTML.
function Inline({ text }) {
  return text.split(/(https?:\/\/[^\s<>]+)/g).map((part, i) =>
    /^https?:\/\//.test(part) ? (
      <ExternalLink url={part} key={i}>
        {part}
      </ExternalLink>
    ) : (
      part
    ),
  );
}
export function AnswerText({ text }) {
  return String(text || "")
    .split(/\n\s*\n/)
    .map((paragraph, i) => {
      const lines = paragraph.split("\n");
      if (lines.every((line) => /^\s*[-*•]\s+/.test(line)))
        return (
          <ul key={i}>
            {lines.map((line, j) => (
              <li key={j}>
                <Inline text={line.replace(/^\s*[-*•]\s+/, "")} />
              </li>
            ))}
          </ul>
        );
      if (lines.every((line) => /^\s*\d+[.)]\s+/.test(line)))
        return (
          <ol key={i}>
            {lines.map((line, j) => (
              <li key={j}>
                <Inline text={line.replace(/^\s*\d+[.)]\s+/, "")} />
              </li>
            ))}
          </ol>
        );
      return (
        <p key={i}>
          <Inline text={paragraph} />
        </p>
      );
    });
}
function Feedback({ answer, t }) {
  const [selected, setSelected] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function send(helpful) {
    setBusy(true);
    setError("");
    try {
      await assistantRequest("feedback", {
        answer_id: answer.answer_id,
        helpful,
      });
      setSelected(helpful);
    } catch {
      setError(t.error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <span className="chat-feedback">
      {[
        [true, "♧", t.helpful],
        [false, "♧", t.unhelpful],
      ].map(([value, , label]) => (
        <button
          className="chat-icon-button"
          title={label}
          aria-label={label}
          aria-pressed={selected === value}
          disabled={busy}
          onClick={() => send(value)}
          key={String(value)}
        >
          {value ? "👍" : "👎"}
        </button>
      ))}
      <span role="status" className="chat-feedback-status">
        {error || (selected !== null ? t.saved : "")}
      </span>
    </span>
  );
}
export default function AssistantMessages({
  messages,
  t,
  onChoice,
  onNavigate,
  onListen,
  onStop,
  audioState,
  busy,
}) {
  return messages.map((message) =>
    message.role === "user" ? (
      <div className="chat-message chat-user" key={message.id}>
        <div>{message.text}</div>
      </div>
    ) : (
      <article
        className="chat-message chat-assistant"
        key={message.id}
        lang={message.answer.language?.split("-")[0]}
      >
        <div className="chat-avatar" aria-hidden="true">
          ✦
        </div>
        <div className="chat-answer">
          <AnswerText text={message.answer.text} />
          {(message.answer.warnings || []).map((warning, i) => (
            <p className="chat-warning" key={i}>
              {warning}
            </p>
          ))}
          {!!message.answer.choices?.length && (
            <div className="chat-chips">
              {message.answer.choices.map((choice) => (
                <button
                  disabled={busy}
                  key={choice}
                  onClick={() => onChoice(message.answer, choice)}
                >
                  {choice}
                </button>
              ))}
            </div>
          )}
          {message.answer.action && (
            <button
              className="chat-navigation"
              onClick={() => onNavigate(message.answer.action)}
            >
              {t.actions[message.answer.action] || t.general}{" "}
              <span aria-hidden="true">↗</span>
            </button>
          )}
          {!!message.answer.references?.length && (
            <details className="chat-sources">
              <summary>{t.sources}</summary>
              {message.answer.references.map((r, i) => (
                <p key={i}>
                  {r.id} · {r.observed_at || "Observation date not provided"}
                  <br />
                  {r.label}
                </p>
              ))}
            </details>
          )}
          <div className="chat-answer-actions">
            {message.answer.audio_available ? (
              <>
                <button
                  className="chat-audio"
                  disabled={audioState.loading}
                  onClick={() => onListen(message.answer)}
                >
                  <span aria-hidden="true">🔊</span>{" "}
                  {audioState.loading &&
                  audioState.id === message.answer.answer_id
                    ? t.audioLoading
                    : message.answer.language !==
                        message.answer.requested_language
                      ? t.listenEnglish
                      : audioState.id === message.answer.answer_id
                        ? t.replay
                        : t.listen}
                </button>
                {audioState.playing &&
                  audioState.id === message.answer.answer_id && (
                    <button className="chat-audio" onClick={onStop}>
                      ■ {t.stop}
                    </button>
                  )}
              </>
            ) : (
              <div className="chat-audio-unavailable">
                <button className="chat-audio" disabled>
                  <span aria-hidden="true">🔊</span> {t.listen}
                </button>
                <p>
                  {t.audioReasons[message.answer.audio_unavailable_reason] ||
                    t.speechError}
                </p>
              </div>
            )}
            <Feedback answer={message.answer} t={t} />
          </div>
        </div>
      </article>
    ),
  );
}
