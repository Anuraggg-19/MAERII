import React, { useEffect, useRef, useState } from "react";
import { useWorkspace } from "../../contexts/Workspace";
import { assistantRequest } from "../../services/api";
import {
  readPreference,
  writePreference,
  stableStringify,
} from "../../utils/workflow";
import { languages, copy } from "./language";
import AssistantMessages from "./AssistantMessages";

export default function Assistant({ findMaterial }) {
  const w = useWorkspace();
  const [open, setOpen] = useState(false),
    [menu, setMenu] = useState(false);
  const [language, setLanguage] = useState(() => {
    const value = readPreference("maerii-assistant-language", null);
    return languages[value] ? value : null;
  });
  const [messages, setMessages] = useState([]),
    [questions, setQuestions] = useState([]),
    [text, setText] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(null);
  const [audioState, setAudioState] = useState({
    loading: false,
    playing: false,
    id: null,
  });
  const [mobile, setMobile] = useState(
    () => window.matchMedia("(max-width: 600px)").matches,
  );
  const [newMessages, setNewMessages] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const t = copy[language || "en-IN"];
  const launcher = useRef(null),
    panel = useRef(null),
    composer = useRef(null),
    scroll = useRef(null);
  const controller = useRef(null),
    epoch = useRef(0),
    audio = useRef(null),
    audioEpoch = useRef(0),
    atBottom = useRef(true);
  const contextKey = stableStringify(w.context);
  const context = JSON.parse(contextKey);

  function stopAudio() {
    audioEpoch.current++;
    if (audio.current) {
      audio.current.pause();
      audio.current.src = "";
      audio.current = null;
    }
    setAudioState((s) => ({ ...s, loading: false, playing: false }));
  }
  function cancel() {
    epoch.current++;
    controller.current?.abort();
    setBusy(false);
    stopAudio();
  }
  function close() {
    cancel();
    setOpen(false);
    setMenu(false);
    launcher.current?.focus();
  }
  function chooseLanguage(value) {
    cancel();
    setLanguage(value);
    setMenu(false);
    setError("");
    setRetry(null);
    writePreference("maerii-assistant-language", value);
  }

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 600px)");
    const update = () => setMobile(mq.matches);
    mq.addEventListener("change", update);
    return () => {
      mq.removeEventListener("change", update);
      controller.current?.abort();
      audioEpoch.current++;
      audio.current?.pause();
    };
  }, []);
  useEffect(() => {
    cancel();
    setError("");
    setRetry(null);
  }, [contextKey, language]);
  useEffect(() => {
    if (open) panel.current?.querySelector("button")?.focus();
  }, [open]);
  useEffect(() => {
    if (!open || !language || !w.capabilities?.enabled) return;
    const abort = new AbortController();
    setQuestions([]);
    assistantRequest(
      "suggestions",
      { language, context: JSON.parse(contextKey) },
      abort.signal,
    )
      .then((data) =>
        setQuestions([...(data.suggestions || []), ...(data.more || [])]),
      )
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => abort.abort();
  }, [contextKey, language, open, w.capabilities?.enabled]);
  useEffect(() => {
    if (atBottom.current && scroll.current)
      scroll.current.scrollTop = scroll.current.scrollHeight;
    else if (messages.length) setNewMessages(true);
  }, [messages, busy]);
  useEffect(() => {
    if (composer.current) {
      composer.current.style.height = "auto";
      composer.current.style.height =
        Math.min(composer.current.scrollHeight, 112) + "px";
    }
  }, [text]);

  async function ask(fields, label, override = {}) {
    if (busy || !language) return;
    cancel();
    const current = epoch.current;
    controller.current = new AbortController();
    setBusy(true);
    setError("");
    setRetry(null);
    setText("");
    setMoreOpen(false);
    const ctx = { ...context, ...override };
    const next = { fields, label, override };
    setMessages((old) => [
      ...old,
      { id: crypto.randomUUID(), role: "user", text: label },
    ]);
    atBottom.current = true;
    try {
      const answer = await assistantRequest(
        "answer",
        { ...fields, language, context: ctx },
        controller.current.signal,
      );
      if (current !== epoch.current) return;
      if (typeof answer.text !== "string" || !answer.text.trim())
        throw new Error(t.error);
      setMessages((old) => [
        ...old,
        { id: crypto.randomUUID(), role: "assistant", answer },
      ]);
    } catch (e) {
      if (current === epoch.current && e.name !== "AbortError") {
        setError(e.message);
        setRetry(next);
      }
    } finally {
      if (current === epoch.current) {
        setBusy(false);
        composer.current?.focus();
      }
    }
  }
  async function listen(answer) {
    stopAudio();
    const current = audioEpoch.current;
    setAudioState({ id: answer.answer_id, loading: true, playing: false });
    setError("");
    try {
      const result = await assistantRequest("audio", {
        answer_id: answer.answer_id,
      });
      if (current !== audioEpoch.current) return;
      if (!/^\/api\/assistant\/audio\/[a-f0-9]{64}$/.test(result.url))
        throw new Error("Invalid audio URL");
      const player = new Audio(result.url);
      audio.current = player;
      player.onended = () => {
        if (current === audioEpoch.current)
          setAudioState((s) => ({ ...s, playing: false }));
      };
      await player.play();
      if (current === audioEpoch.current)
        setAudioState({ id: answer.answer_id, loading: false, playing: true });
    } catch {
      if (current === audioEpoch.current) {
        setAudioState((s) => ({ ...s, loading: false, playing: false }));
        setError(t.speechError);
      }
    }
  }
  function navigate(action) {
    close();
    if (action === "search") findMaterial();
    else if (
      ["overview", "categories", "market", "recommendations"].includes(action)
    )
      w.navigate(action);
  }
  function keydown(e) {
    if (e.key === "Escape") {
      e.stopPropagation();
      if (menu) setMenu(false);
      else close();
    }
    if (mobile && e.key === "Tab") {
      const nodes = [
        ...panel.current.querySelectorAll(
          "button,select,textarea,a[href],summary",
        ),
      ].filter((el) => !el.disabled && el.getClientRects().length);
      const first = nodes[0],
        last = nodes.at(-1);
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    }
  }
  if (w.capabilities?.enabled === false) return null;
  if (!w.capabilities && !w.assistantError) return null;
  return (
    <div className="assistant-root">
      <button
        ref={launcher}
        className={"assistant-launcher " + (open ? "is-open" : "")}
        title="MAERII Assistant"
        aria-label={open ? t.close : "Open MAERII Assistant"}
        aria-expanded={open}
        aria-controls="assistant-panel"
        onClick={() => (open ? close() : setOpen(true))}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 3v-3a2 2 0 0 1-2-2V6a2 2 0 0 1 3-2Z" />
          <path d="M7 9h10M7 13h6" />
        </svg>
        <span className="launcher-label">Ask MAERII</span>
      </button>
      {open && (
        <>
          {mobile && <div className="chat-backdrop" onClick={close} />}
          <section
            id="assistant-panel"
            className="assistant-panel"
            ref={panel}
            role="dialog"
            aria-modal={mobile || undefined}
            aria-labelledby="assistant-title"
            lang={(language || "en-IN").split("-")[0]}
            onKeyDown={keydown}
          >
            <header className="chat-header">
              <span className="chat-brand-icon" aria-hidden="true">
                ✦
              </span>
              <div className="chat-heading">
                <h2 id="assistant-title">{t.title}</h2>
                <p>{t.subtitle}</p>
              </div>
              <button
                className="chat-icon-button"
                aria-label={t.menu}
                aria-expanded={menu}
                onClick={() => setMenu(!menu)}
              >
                ⋯
              </button>
              <button
                className="chat-icon-button"
                aria-label={t.close}
                onClick={close}
              >
                ×
              </button>
              {menu && (
                <div className="chat-options">
                  <label>
                    {t.language}
                    <select
                      aria-label={t.language}
                      value={language || ""}
                      onChange={(e) => chooseLanguage(e.target.value)}
                    >
                      <option value="" disabled>
                        {t.resetNote}
                      </option>
                      {Object.entries(languages).map(([code, name]) => (
                        <option key={code} value={code}>
                          {name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    onClick={() => {
                      cancel();
                      setMessages([]);
                      setError("");
                      setRetry(null);
                      setMenu(false);
                    }}
                  >
                    {t.clear}
                  </button>
                  <button onClick={() => chooseLanguage(null)}>
                    {t.reset}
                  </button>
                  <p>{t.pilot}</p>
                </div>
              )}
            </header>
            <div className="chat-context">
              <span className="chat-context-dot" />
              {w.material ? `${t.discussing}: ${w.material.name}` : t.general}
              <span className="chat-language">{languages[language] || ""}</span>
            </div>
            <div
              className="chat-conversation"
              ref={scroll}
              onScroll={() => {
                if (scroll.current) {
                  atBottom.current =
                    scroll.current.scrollHeight -
                      scroll.current.scrollTop -
                      scroll.current.clientHeight <
                    70;
                  if (atBottom.current) setNewMessages(false);
                }
              }}
            >
              {w.assistantError ? (
                <div className="chat-welcome">
                  <h3>{t.unavailable}</h3>
                  <p>{w.assistantError}</p>
                  <button
                    className="chat-navigation"
                    onClick={w.retryAssistant}
                  >
                    {t.retry}
                  </button>
                </div>
              ) : !language ? (
                <div className="chat-welcome">
                  <span className="welcome-eyebrow">
                    WELCOME · स्वागत · स्वागत
                  </span>
                  <h3>
                    Your language.
                    <br />
                    Your next step.
                  </h3>
                  <p>
                    Choose a language to get started.
                    <br />
                    अपनी भाषा चुनें · तुमची भाषा निवडा
                  </p>
                  <div className="chat-language-choices">
                    {Object.entries(languages).map(([code, name]) => (
                      <button key={code} onClick={() => chooseLanguage(code)}>
                        {name}
                        <span aria-hidden="true">→</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  {!messages.length && (
                    <div className="chat-welcome">
                      <span className="welcome-eyebrow">MAERII GUIDE</span>
                      <h3>{t.welcome}</h3>
                      <p>{t.intro}</p>
                      <div className="chat-chips" aria-label={t.options}>
                        {questions.slice(0, 4).map((q) => (
                          <button
                            disabled={busy}
                            key={q.id}
                            onClick={() => ask({ question_id: q.id }, q.label)}
                          >
                            {q.label}
                            <span aria-hidden="true">↗</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  <div
                    className="chat-message-log"
                    role="log"
                    aria-live="polite"
                    aria-relevant="additions"
                  >
                    <AssistantMessages
                      messages={messages}
                      t={t}
                      busy={busy}
                      audioState={audioState}
                      onListen={listen}
                      onStop={stopAudio}
                      onNavigate={navigate}
                      onChoice={(answer, choice) =>
                        answer.question_id === "Q05"
                          ? ask({ question_id: "Q05", term: choice }, choice)
                          : ask({ question_id: answer.question_id }, choice, {
                              product: choice,
                            })
                      }
                    />
                  </div>
                  {busy && (
                    <div className="chat-typing" role="status">
                      <span />
                      <span />
                      <span />
                      <span className="sr-only">{t.working}</span>
                    </div>
                  )}
                  {!!questions.length && (
                    <details
                      className="chat-more"
                      open={moreOpen}
                      onToggle={(e) => setMoreOpen(e.currentTarget.open)}
                    >
                      <summary>{t.more}</summary>
                      <div className="chat-chips">
                        {questions.map((q) => (
                          <button
                            key={q.id}
                            disabled={busy}
                            onClick={() => ask({ question_id: q.id }, q.label)}
                          >
                            {q.label}
                          </button>
                        ))}
                      </div>
                    </details>
                  )}
                </>
              )}
              {error && (
                <div className="chat-error" role="alert">
                  {error}
                  {retry && (
                    <button
                      onClick={() =>
                        ask(retry.fields, retry.label, retry.override)
                      }
                      disabled={busy}
                    >
                      {t.retry}
                    </button>
                  )}
                </div>
              )}
            </div>
            {newMessages && (
              <button
                className="chat-latest"
                onClick={() => {
                  scroll.current.scrollTop = scroll.current.scrollHeight;
                  setNewMessages(false);
                  atBottom.current = true;
                }}
              >
                {t.newMessages} ↓
              </button>
            )}
            <footer className="chat-footer">
              <form
                className="chat-composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (text.trim()) ask({ text: text.trim() }, text.trim());
                }}
              >
                <textarea
                  ref={composer}
                  aria-label={t.placeholder}
                  placeholder={t.placeholder}
                  rows="1"
                  maxLength="500"
                  value={text}
                  disabled={!language || !!w.assistantError}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      !e.shiftKey &&
                      !e.nativeEvent.isComposing
                    ) {
                      e.preventDefault();
                      if (text.trim() && !busy)
                        ask({ text: text.trim() }, text.trim());
                    }
                  }}
                />
                <button
                  type="submit"
                  aria-label={t.send}
                  disabled={
                    !language || !text.trim() || busy || !!w.assistantError
                  }
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="m4 4 17 8-17 8 3-8-3-8Zm3 8h14" />
                  </svg>
                </button>
              </form>
              <p className="chat-footnote">{t.privacy}</p>
            </footer>
          </section>
        </>
      )}
    </div>
  );
}
