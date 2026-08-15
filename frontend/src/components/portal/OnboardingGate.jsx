import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, ArrowLeft, Loader2, Check, Sparkles } from "lucide-react";
import { usePortal } from "@/contexts/PortalContext";
import { toast } from "sonner";

/** The first-login interview. Ten questions, and the portal waits behind them.
 *
 *  The owner chose a hard gate over a skippable one, so this screen is the only
 *  thing a new member or client sees. That decision costs something real —
 *  someone opening the portal to check one invoice meets nine questions first —
 *  and everything here is built to pay it back:
 *
 *  - One question at a time, so it reads as being asked rather than as a form.
 *  - **Saved on every step.** Answer six, lose your connection, come back: the
 *    six are still there and you resume at seven.
 *  - Resumes at the first *unanswered* question, not at the beginning.
 *  - It says why it is asking, once, at the top. A wall with no explanation is
 *    the version people close the tab on.
 */

const EASE = [0.16, 1, 0.3, 1];

function ProgressRail({ total, index, answered }) {
  return (
    <div className="flex items-center gap-1.5" aria-hidden="true">
      {Array.from({ length: total }, (_, i) => (
        <motion.span
          key={i}
          className="h-1 flex-1 rounded-full"
          initial={false}
          animate={{
            backgroundColor:
              i === index
                ? "hsl(190 100% 50%)"
                : answered[i]
                ? "hsl(190 100% 50% / 0.35)"
                : "rgba(255,255,255,0.09)",
            // The current step is taller, so the eye finds "where am I" before
            // it has to count filled segments.
            scaleY: i === index ? 2.2 : 1,
          }}
          transition={{ duration: 0.3, ease: EASE }}
        />
      ))}
    </div>
  );
}

export default function OnboardingGate() {
  const { questions, answers, saveAnswer, name, role, reload } = usePortal();

  // Resume where they stopped. Starting at zero would make someone who answered
  // eight re-read all eight to find the ninth.
  const firstUnanswered = useMemo(() => {
    const at = questions.findIndex((q) => !String(answers[q.key] || "").trim());
    return at === -1 ? 0 : at;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const [index, setIndex] = useState(firstUnanswered);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [direction, setDirection] = useState(1);
  const [finishing, setFinishing] = useState(false);
  const inputRef = useRef(null);

  const question = questions[index];
  const total = questions.length;
  const answeredFlags = questions.map((q) => Boolean(String(answers[q.key] || "").trim()));

  useEffect(() => {
    setValue(String(answers[question?.key] || ""));
    // Focus the field, but not on a phone: a keyboard springing up over the
    // question you are meant to be reading is worse than one extra tap.
    if (window.matchMedia("(pointer: fine)").matches) {
      setTimeout(() => inputRef.current?.focus(), 260);
    }
  }, [index]); // eslint-disable-line react-hooks/exhaustive-deps

  const go = (next) => {
    setDirection(next > index ? 1 : -1);
    setIndex(next);
  };

  const submit = async (override) => {
    const answer = String(override ?? value).trim();
    if (!answer || busy) return;
    setBusy(true);
    try {
      const result = await saveAnswer(question.key, answer);
      if (result.onboarding_complete) {
        setFinishing(true);
        // A beat on the closing card, then the portal. Cutting straight from
        // the last question to the dashboard reads as the form having crashed.
        setTimeout(() => reload(), 1400);
        return;
      }
      const nextUnanswered = questions.findIndex(
        (q, i) => i > index && !String(answers[q.key] || "").trim()
      );
      go(nextUnanswered === -1 ? Math.min(index + 1, total - 1) : nextUnanswered);
    } catch {
      toast.error("That didn't save. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  };

  if (!question) return null;

  const isChoice = question.kind === "choice";
  const isLong = question.kind === "long";

  return (
    <div className="fixed inset-0 z-[100] overflow-y-auto bg-black" data-testid="onboarding-gate">
      <div className="obx-aurora pointer-events-none fixed inset-0" />

      <div className="relative z-10 mx-auto flex min-h-[100dvh] w-full max-w-xl flex-col px-5 py-8 sm:px-6">
        <AnimatePresence mode="wait">
          {finishing ? (
            <motion.div
              key="done"
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5, ease: EASE }}
              className="flex flex-1 flex-col items-center justify-center text-center"
            >
              <div className="obx-holo obx-glass relative flex h-20 w-20 items-center justify-center overflow-hidden rounded-3xl">
                <Check className="relative z-10 h-8 w-8 text-primary" />
              </div>
              <h1 className="mt-6 font-display text-2xl font-bold tracking-tight">
                That&apos;s everything.
              </h1>
              <p className="mt-2 max-w-sm text-sm leading-relaxed text-graphite">
                Your assistant has it now. You won&apos;t be asked again.
              </p>
            </motion.div>
          ) : (
            <motion.div key="form" className="flex flex-1 flex-col">
              <header className="shrink-0">
                <div className="flex items-center gap-2">
                  <div className="obx-holo obx-glass relative flex h-8 w-8 items-center justify-center overflow-hidden rounded-xl">
                    <Sparkles className="relative z-10 h-3.5 w-3.5 text-primary" />
                  </div>
                  <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
                    {role === "founding" ? "Founding Circle" : "Obrinex"} · Setting up
                  </p>
                  <span className="obx-figure ml-auto font-mono text-[11px] text-carbon">
                    {String(index + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
                  </span>
                </div>
                <div className="mt-3">
                  <ProgressRail total={total} index={index} answered={answeredFlags} />
                </div>
              </header>

              <div className="flex flex-1 flex-col justify-center py-8">
                {index === 0 && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.15 }}
                    className="mb-6 max-w-prose text-sm leading-relaxed text-graphite"
                  >
                    {name ? `${name.split(" ")[0]} — ` : ""}before you go in, {total} questions.
                    They&apos;re what your assistant remembers about you, so you never have to
                    explain yourself twice. Nothing here is scored, and nobody else sees it.
                  </motion.p>
                )}

                <AnimatePresence mode="wait" custom={direction}>
                  <motion.div
                    key={question.key}
                    custom={direction}
                    initial={{ opacity: 0, x: direction * 26 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: direction * -26 }}
                    transition={{ duration: 0.34, ease: EASE }}
                  >
                    <h1 className="font-display text-2xl font-bold leading-tight tracking-tight sm:text-3xl">
                      {question.prompt}
                    </h1>
                    {question.hint && (
                      <p className="mt-2 max-w-prose text-sm leading-relaxed text-graphite">
                        {question.hint}
                      </p>
                    )}

                    <div className="mt-6">
                      {isChoice ? (
                        <div className="grid gap-2 sm:grid-cols-2">
                          {question.options.map((option, i) => {
                            const chosen = value === option;
                            return (
                              <motion.button
                                key={option}
                                initial={{ opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.05 + i * 0.035, ease: EASE }}
                                onClick={() => { setValue(option); submit(option); }}
                                disabled={busy}
                                data-testid={`onboarding-option-${i}`}
                                className={`obx-glass obx-lift obx-sheen rounded-xl px-4 py-3 text-left text-sm transition-colors ${
                                  chosen ? "border-primary/45 text-primary" : ""
                                }`}
                              >
                                {option}
                              </motion.button>
                            );
                          })}
                        </div>
                      ) : isLong ? (
                        <textarea
                          ref={inputRef}
                          rows={5}
                          value={value}
                          maxLength={question.max_length}
                          onChange={(e) => setValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
                          }}
                          placeholder={question.placeholder || ""}
                          data-testid="onboarding-input"
                          className="obx-glass w-full resize-y rounded-xl px-4 py-3 text-base outline-none focus:border-primary/45 placeholder:text-carbon"
                        />
                      ) : (
                        <input
                          ref={inputRef}
                          value={value}
                          maxLength={question.max_length}
                          onChange={(e) => setValue(e.target.value)}
                          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
                          placeholder={question.placeholder || ""}
                          data-testid="onboarding-input"
                          className="obx-glass w-full rounded-xl px-4 py-3.5 text-base outline-none focus:border-primary/45 placeholder:text-carbon"
                        />
                      )}
                    </div>
                  </motion.div>
                </AnimatePresence>
              </div>

              <footer className="flex shrink-0 items-center gap-3">
                <button
                  onClick={() => go(Math.max(0, index - 1))}
                  disabled={index === 0}
                  data-testid="onboarding-back"
                  className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm text-graphite transition-colors hover:text-foreground disabled:pointer-events-none disabled:opacity-30"
                >
                  <ArrowLeft className="h-3.5 w-3.5" /> Back
                </button>

                {!isChoice && (
                  <button
                    onClick={() => submit()}
                    disabled={busy || !value.trim()}
                    data-testid="onboarding-next"
                    className="ml-auto flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-medium text-background transition-opacity disabled:opacity-30"
                  >
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    {index === total - 1 ? "Finish" : "Next"}
                    {!busy && <ArrowRight className="h-3.5 w-3.5" />}
                  </button>
                )}
              </footer>

              <p className="mt-3 shrink-0 text-center font-mono text-[9px] uppercase tracking-[0.16em] text-carbon">
                Saved as you go · {answeredFlags.filter(Boolean).length} of {total} answered
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
