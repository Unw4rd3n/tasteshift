import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import {
  ArrowRight,
  ArrowUpRight,
  BookmarkSimple,
  Check,
  Pause,
  Play,
  Plus,
  MagnifyingGlass,
  X,
} from "@phosphor-icons/react";
import {
  createDiscovery,
  safeWebsite,
  searchEntities,
  sendFeedback,
} from "./api";
import { previewPicks, previewSeeds } from "./preview";
import {
  LEVELS,
  categoryLabel,
  tagLabel,
  type Category,
  type Discovery,
  type Entity,
  type Feedback,
  type Level,
  type Pick,
  type SavedPick,
} from "./types";

const planetAssets = [
  "planet-violet",
  "planet-ice",
  "planet-rust",
  "planet-moon",
  "planet-ocean",
  "planet-jupiter",
];
const positions = [
  [42, 20, 132],
  [82, 32, 112],
  [12, 39, 90],
  [19, 70, 90],
  [48, 83, 148],
  [78, 66, 156],
];
const assetFor = (index: number) =>
  `/assets/${planetAssets[index % planetAssets.length]}.webp`;
const savedKey = "tasteshift.saved.v1";
function readSaved(): SavedPick[] {
  try {
    const raw = JSON.parse(localStorage.getItem(savedKey) || "[]");
    if (!Array.isArray(raw)) return [];
    return raw
      .filter(
        (value) =>
          value &&
          typeof value.preview === "boolean" &&
          (value.discoveryId === null ||
            typeof value.discoveryId === "string") &&
          typeof value.pick?.entity?.id === "string" &&
          typeof value.pick.entity.name === "string" &&
          ["artist", "movie", "book"].includes(value.pick.entity.category) &&
          typeof value.pick.explanation === "string" &&
          Array.isArray(value.pick.shared_tags),
      )
      .slice(0, 100);
  } catch {
    return [];
  }
}
function Dialog({
  title,
  onClose,
  children,
  className = "",
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    dialog?.querySelector<HTMLInputElement>("input")?.focus();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={`dialog ${className}`}
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="dialog-content">
        <div className="dialog-heading">
          <h2>{title}</h2>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={22} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
function SeedPicker({
  initial,
  level,
  initialIntention,
  onClose,
  onDiscover,
}: {
  initial: Entity[];
  level: Level;
  initialIntention: string;
  onClose: () => void;
  onDiscover: (seeds: Entity[], intention: string) => void;
}) {
  const [seeds, setSeeds] = useState(initial);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<Category>("artist");
  const [results, setResults] = useState<Entity[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [intention, setIntention] = useState(initialIntention);
  useEffect(() => {
    const controller = new AbortController();
    setResults([]);
    setError("");
    setSearching(false);
    if (query.trim().length < 2) return;
    setSearching(true);
    const timer = window.setTimeout(async () => {
      try {
        const entities = await searchEntities(
          query.trim(),
          category,
          controller.signal,
        );
        if (!controller.signal.aborted) setResults(entities);
      } catch (error) {
        if (!controller.signal.aborted)
          setError(
            error instanceof Error ? error.message : "Search is unavailable.",
          );
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, category]);
  return (
    <Dialog
      title="Your starting point"
      onClose={onClose}
      className="seed-dialog"
    >
      <p className="dialog-intro">
        Pick 3–5 artists, films or books you love. We’ll find the connections
        between them.
      </p>
      <div className="draft-seeds" aria-label="Selected interests">
        {seeds.map((seed) => (
          <button
            className="seed-chip"
            key={seed.id}
            onClick={() =>
              setSeeds(seeds.filter((item) => item.id !== seed.id))
            }
            aria-label={`Remove ${seed.name}`}
          >
            {seed.name}
            <X size={14} />
          </button>
        ))}
        {!seeds.length && (
          <span className="muted">Your interests will appear here.</span>
        )}
      </div>
      <div className="category-switch" aria-label="Search category">
        {(["artist", "movie", "book"] as Category[]).map((value) => (
          <button
            key={value}
            aria-pressed={category === value}
            onClick={() => setCategory(value)}
          >
            {categoryLabel[value]}
            {value === "movie" || value === "book" ? "s" : ""}
          </button>
        ))}
      </div>
      <label className="search-field">
        <MagnifyingGlass size={20} />
        <input
          autoFocus
          maxLength={120}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={`Search ${category === "artist" ? "an artist" : category === "movie" ? "a film" : "a book"}…`}
          aria-label="Search your interests"
        />
      </label>
      <div className="search-results" aria-live="polite" aria-busy={searching}>
        {searching ? (
          <p className="muted">Searching the catalog…</p>
        ) : error ? (
          <p className="inline-error" role="alert">
            {error}
          </p>
        ) : results.length ? (
          results.map((entity) => {
            const added = seeds.some((seed) => seed.id === entity.id);
            return (
              <button
                key={entity.id}
                className="search-result"
                disabled={added || seeds.length >= 5}
                onClick={() => {
                  setSeeds([...seeds, entity]);
                  setQuery("");
                }}
              >
                <span>
                  <strong>{entity.name}</strong>
                  <small>{categoryLabel[entity.category]}</small>
                </span>
                {added ? <Check size={20} /> : <Plus size={20} />}
              </button>
            );
          })
        ) : query.trim().length >= 2 ? (
          <p className="muted">
            No matches. Try a different title or category.
          </p>
        ) : (
          <p className="muted">
            Try David Bowie, Spirited Away or a favourite book.
          </p>
        )}
      </div>
      <label className="intention-field">
        Something in mind?{" "}
        <span className="muted">Optional · uses the experience planner</span>
        <textarea
          value={intention}
          onChange={(event) => setIntention(event.target.value)}
          maxLength={600}
          rows={2}
          placeholder="A quiet evening with something unfamiliar…"
        />
      </label>
      <div className="dialog-footer">
        <span className="muted">
          {seeds.length} of 5 interests · {level}
        </span>
        <button
          className="primary-button"
          disabled={seeds.length < 3 || intention.trim().length === 1}
          onClick={() => onDiscover(seeds, intention)}
        >
          Build my system <ArrowRight size={22} />
        </button>
      </div>
    </Dialog>
  );
}
export function App() {
  const [discovery, setDiscovery] = useState<Discovery | null>(null);
  const [seeds, setSeeds] = useState<Entity[]>([]);
  const [level, setLevel] = useState<Level>("experimental");
  const [intention, setIntention] = useState("");
  const [selectedId, setSelectedId] = useState(previewPicks[0].entity.id);
  const [picker, setPicker] = useState(false);
  const [savedOpen, setSavedOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [saved, setSaved] = useState<SavedPick[]>(readSaved);
  const [busy, setBusy] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [paused, setPaused] = useState(false);
  const [hidden, setHidden] = useState(document.hidden);
  const [reduced, setReduced] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const requestRef = useRef<AbortController | null>(null);
  const pendingRef = useRef(false);
  const requestKey = useRef<{ input: string; key: string } | null>(null);
  const retryRef = useRef<(() => void) | null>(null);
  const workspaceRef = useRef<HTMLElement | null>(null);
  const detailRef = useRef<HTMLElement | null>(null);
  const isPreview = !discovery;
  const picks = discovery ? discovery.items : previewPicks;
  const selected =
    picks.find((pick) => pick.entity.id === selectedId) || picks[0];
  const selectedIndex = selected ? Math.max(0, picks.indexOf(selected)) : 0;
  const isSaved =
    selected &&
    saved.some((item) => item.pick.entity.id === selected.entity.id);
  const motionOff = paused || reduced || hidden;
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onMotion = () => setReduced(query.matches);
    const onVisibility = () => setHidden(document.hidden);
    query.addEventListener("change", onMotion);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      query.removeEventListener("change", onMotion);
      document.removeEventListener("visibilitychange", onVisibility);
      requestRef.current?.abort();
    };
  }, []);
  useEffect(() => {
    const workspace = workspaceRef.current;
    if (!workspace || motionOff) return;
    let frame = 0;
    const move = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const rect = workspace.getBoundingClientRect();
        workspace.style.setProperty(
          "--parallax-x",
          `${((event.clientX - rect.left) / rect.width - 0.5) * 8}px`,
        );
        workspace.style.setProperty(
          "--parallax-y",
          `${((event.clientY - rect.top) / rect.height - 0.5) * 8}px`,
        );
      });
    };
    const reset = () => {
      workspace.style.setProperty("--parallax-x", "0px");
      workspace.style.setProperty("--parallax-y", "0px");
    };
    workspace.addEventListener("pointermove", move);
    workspace.addEventListener("pointerleave", reset);
    return () => {
      cancelAnimationFrame(frame);
      workspace.removeEventListener("pointermove", move);
      workspace.removeEventListener("pointerleave", reset);
      reset();
    };
  }, [motionOff]);
  async function discover(
    nextSeeds: Entity[],
    nextLevel: Level,
    nextIntention: string,
  ) {
    if (nextSeeds.length < 3 || pendingRef.current) return;
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    pendingRef.current = true;
    const input = JSON.stringify({
      seeds: nextSeeds.map((seed) => seed.id),
      level: nextLevel,
      intention: nextIntention.trim(),
    });
    if (requestKey.current?.input !== input)
      requestKey.current = { input, key: crypto.randomUUID() };
    setPicker(false);
    setBusy(true);
    setError("");
    setNotice("");
    retryRef.current = () => {
      void discover(nextSeeds, nextLevel, nextIntention);
    };
    try {
      const result = await createDiscovery(
        nextSeeds,
        nextLevel,
        nextIntention,
        requestKey.current!.key,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setDiscovery(result);
      setSeeds(nextSeeds);
      setLevel(result.level);
      setIntention(nextIntention);
      setSelectedId(result.items[0]?.entity.id || "");
      setDetailOpen(false);
      requestKey.current = null;
      retryRef.current = null;
    } catch (error) {
      if (!controller.signal.aborted)
        setError(
          error instanceof Error
            ? error.message
            : "Could not build your system.",
        );
    } finally {
      pendingRef.current = false;
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  async function feedback(action: Feedback) {
    if (!selected || feedbackBusy) return;
    setFeedbackBusy(true);
    setError("");
    try {
      if (discovery)
        await sendFeedback(discovery.id, selected.entity.id, action);
      if (action === "save") {
        const entry: SavedPick = {
          pick: selected,
          discoveryId: discovery?.id || null,
          preview: isPreview,
        };
        const next = [
          entry,
          ...saved.filter((item) => item.pick.entity.id !== selected.entity.id),
        ].slice(0, 100);
        setSaved(next);
        try {
          localStorage.setItem(savedKey, JSON.stringify(next));
          setNotice(
            isPreview
              ? "Sample pick saved on this device."
              : "Saved to your discoveries.",
          );
        } catch {
          setNotice("Saved for this visit. Device storage is unavailable.");
        }
      } else
        setNotice(
          action === "not_for_me"
            ? "Noted. This will shape your next discovery."
            : "Noted. Next time we’ll look for something new.",
        );
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not save your feedback.",
      );
    } finally {
      setFeedbackBusy(false);
    }
  }
  const website = safeWebsite(selected?.entity.website_url);
  return (
    <div className="app-shell" data-motion-off={motionOff}>
      <a className="skip-link" href="#starting-point">
        Skip to controls
      </a>
      <header className="brand-header">
        <a
          href="#"
          className="wordmark"
          aria-label="TasteShift home"
          onClick={(event) => {
            event.preventDefault();
            setDetailOpen(false);
            setSavedOpen(false);
          }}
        >
          TasteShift
        </a>
      </header>
      <nav className="top-actions" aria-label="Your discoveries">
        <button className="saved-button" onClick={() => setSavedOpen(true)}>
          Saved
          {saved.length > 0 && (
            <span className="saved-count">{saved.length}</span>
          )}
          <BookmarkSimple size={21} weight="light" />
        </button>
        <button
          className="icon-button motion-toggle"
          onClick={() => setPaused(!paused)}
          aria-label={paused ? "Resume animations" : "Pause animations"}
          aria-pressed={paused}
          disabled={reduced}
          title={
            reduced
              ? "Reduced motion is enabled on your device"
              : paused
                ? "Resume animations"
                : "Pause animations"
          }
        >
          {paused || reduced ? <Play size={17} /> : <Pause size={17} />}
        </button>
      </nav>
      <main
        className="workspace"
        ref={workspaceRef}
        aria-label="Your discovery system"
        aria-busy={busy}
      >
        <div className="space-backdrop" aria-hidden="true" />
        <div className="system" data-level={level}>
          <img
            className="orbit-lines"
            src="/assets/orbits.webp"
            alt=""
            draggable="false"
          />
          <div className="sun">
            <img src="/assets/sun.webp" alt="" draggable="false" />
            <span>Your taste</span>
          </div>
          <div className="planets" aria-label="Discoveries">
            {picks.slice(0, 6).map((pick, index) => {
              const [x, y, size] = positions[index];
              const expansion = [0.92, 0.96, 1, 1.04][LEVELS.indexOf(level)];
              const style = {
                "--x": `${50 + (x - 50) * expansion}%`,
                "--y": `${48 + (y - 48) * expansion}%`,
                "--planet-size": `${size}px`,
                "--delay": `${index * 90}ms`,
                "--float-delay": `${-index * 2}s`,
              } as CSSProperties;
              return (
                <button
                  className={`planet ${selected?.entity.id === pick.entity.id ? "is-selected" : ""} ${index < 2 ? "label-above" : ""}`}
                  style={style}
                  key={pick.entity.id}
                  aria-pressed={selected?.entity.id === pick.entity.id}
                  aria-label={`Select ${pick.entity.name}, ${categoryLabel[pick.entity.category]}`}
                  title={pick.entity.name}
                  onClick={() => {
                    setSelectedId(pick.entity.id);
                    setNotice("");
                    if (window.matchMedia("(max-width: 850px)").matches)
                      detailRef.current?.scrollIntoView({
                        behavior: motionOff ? "instant" : "smooth",
                        block: "start",
                      });
                  }}
                >
                  <span className="planet-body">
                    <img src={assetFor(index)} alt="" draggable="false" />
                  </span>
                  <span className="planet-name">{pick.entity.name}</span>
                  <span className="mobile-category">
                    {categoryLabel[pick.entity.category]}
                  </span>
                </button>
              );
            })}
          </div>
          <span className="orbit-caption">
            Further from familiar. <ArrowRight size={20} weight="light" />
          </span>
          {busy && (
            <div className="loading-state" role="status">
              <span>Finding your next orbit…</span>
              <small>Connecting your interests. This can take a moment.</small>
            </div>
          )}
          {!busy && discovery && picks.length === 0 && (
            <div className="loading-state">
              <span>No discoveries this time.</span>
              <small>
                Try different interests or another exploration level.
              </small>
              <button className="text-button" onClick={() => setPicker(true)}>
                Edit my interests
              </button>
            </div>
          )}
        </div>
        <section
          className="starting-point"
          id="starting-point"
          aria-label="Your starting point"
        >
          <div className="seed-heading">
            <span className="eyebrow">Your seeds</span>
            <span className="data-label">
              {isPreview ? "Preview · sample system" : "Live · Qloo"}
            </span>
          </div>
          <div className="seed-row">
            <div className="seed-chips">
              {(isPreview ? previewSeeds : seeds).map((seed) => (
                <button
                  className="seed-chip"
                  key={seed.id}
                  onClick={() => setPicker(true)}
                  disabled={busy}
                >
                  {seed.name}
                </button>
              ))}
            </div>
            <button
              className="edit-seeds"
              onClick={() => setPicker(true)}
              disabled={busy}
            >
              {isPreview ? "Make it yours" : "Edit interests"}
              <Plus size={15} />
            </button>
          </div>
        </section>
        <section className="exploration" aria-label="Exploration distance">
          <span className="exploration-title">Choose how far to explore</span>
          <div
            className="level-selector"
            role="group"
            aria-label="Exploration level"
          >
            {LEVELS.map((value) => (
              <button
                key={value}
                aria-pressed={level === value}
                disabled={busy}
                onClick={() => {
                  if (value === level) return;
                  if (isPreview) setLevel(value);
                  else void discover(seeds, value, intention);
                }}
              >
                <span className="level-dot" aria-hidden="true" />
                <span>{value[0].toUpperCase() + value.slice(1)}</span>
              </button>
            ))}
          </div>
        </section>
      </main>
      <aside
        ref={detailRef}
        className="detail-panel"
        aria-label="Selected discovery"
      >
        {selected ? (
          <div className="detail-content" key={selected.entity.id}>
            <span className="eyebrow category-eyebrow">
              {categoryLabel[selected.entity.category]}
            </span>
            <h1
              className={selected.entity.name.length > 18 ? "long-title" : ""}
            >
              {selected.entity.name}
            </h1>
            <p className="pick-subtitle">
              {isPreview && selected.entity.id === "sample-portishead"
                ? "A darker turn from familiar sounds."
                : selected.entity.description
                  ? selected.entity.description
                  : "A new corner of your taste."}
            </p>
            <section className="reason">
              <h2 className="eyebrow">Why this appeared</h2>
              <p>
                {isPreview
                  ? "Sample pick — choose your interests."
                  : selected.explanation}
              </p>
            </section>
            <button
              className="primary-button explore-button"
              onClick={() => setDetailOpen(true)}
              disabled={busy}
            >
              Explore this pick
              <ArrowRight size={26} weight="light" />
            </button>
            <button
              className="save-pick"
              onClick={() => void feedback("save")}
              disabled={feedbackBusy || isSaved || busy}
            >
              <BookmarkSimple size={25} weight={isSaved ? "fill" : "light"} />
              {isSaved ? "Saved" : feedbackBusy ? "Saving…" : "Save"}
            </button>
            {discovery?.coverage.some(
              (item) => !item.exploration_supported,
            ) && (
              <p className="coverage-note">
                Some categories have limited exploration data. Picks may stay
                the same across levels.
              </p>
            )}
          </div>
        ) : (
          <div className="empty-detail">
            <span className="eyebrow">A little further</span>
            <h1>Something new is out there.</h1>
            <button className="primary-button" onClick={() => setPicker(true)}>
              Choose your interests
              <ArrowRight size={22} />
            </button>
          </div>
        )}
        {(error || notice) && (
          <div className="status-message" aria-live="polite">
            {error ? (
              <>
                <p role="alert">{error}</p>
                {retryRef.current && !busy && (
                  <button
                    className="text-button"
                    onClick={() => retryRef.current?.()}
                  >
                    Try again
                    <ArrowRight size={16} />
                  </button>
                )}
              </>
            ) : (
              <p>{notice}</p>
            )}
          </div>
        )}
      </aside>
      {picker && (
        <SeedPicker
          initial={seeds}
          level={level}
          initialIntention={intention}
          onClose={() => setPicker(false)}
          onDiscover={(draft, text) => void discover(draft, level, text)}
        />
      )}
      {savedOpen && (
        <Dialog title="Saved discoveries" onClose={() => setSavedOpen(false)}>
          <p className="dialog-intro">
            Your finds, kept on this device. Sample picks are labelled
            separately.
          </p>
          {!saved.length ? (
            <div className="empty-saved">
              <BookmarkSimple size={34} weight="light" />
              <p>Keep something that catches your eye.</p>
            </div>
          ) : (
            <div className="saved-list">
              {saved.map((entry) => (
                <article key={entry.pick.entity.id}>
                  <div>
                    <span className="eyebrow">
                      {categoryLabel[entry.pick.entity.category]}
                      {entry.preview ? " · Sample" : ""}
                    </span>
                    <h3>{entry.pick.entity.name}</h3>
                    <p>{entry.pick.explanation}</p>
                  </div>
                  <a
                    href={`https://www.google.com/search?${new URLSearchParams({ q: `${entry.pick.entity.name} ${categoryLabel[entry.pick.entity.category]}` })}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`Search the web for ${entry.pick.entity.name}`}
                  >
                    <ArrowUpRight size={22} />
                  </a>
                </article>
              ))}
            </div>
          )}
        </Dialog>
      )}
      {detailOpen && selected && (
        <Dialog
          title={selected.entity.name}
          onClose={() => setDetailOpen(false)}
          className="pick-dialog"
        >
          <img className="detail-planet" src={assetFor(selectedIndex)} alt="" />
          <span className="eyebrow">
            {categoryLabel[selected.entity.category]}
            {isPreview ? " · Sample pick" : ""}
          </span>
          <p className="detail-explanation">{selected.explanation}</p>
          {selected.entity.description && <p>{selected.entity.description}</p>}
          {selected.shared_tags.length > 0 && (
            <div className="shared-tags" aria-label="Shared cultural tags">
              {selected.shared_tags.slice(0, 5).map((tag) => (
                <span key={tag} title={tag}>
                  {tagLabel(tag)}
                </span>
              ))}
            </div>
          )}
          <a
            className="primary-button external-link"
            href={
              website ||
              `https://www.google.com/search?${new URLSearchParams({ q: `${selected.entity.name} ${categoryLabel[selected.entity.category]}` })}`
            }
            target="_blank"
            rel="noopener noreferrer"
          >
            {website ? "Visit official site" : "Search the web"}
            <ArrowUpRight size={22} />
          </a>
          {!isPreview && (
            <div className="feedback-actions">
              <button
                className="text-button"
                disabled={feedbackBusy}
                onClick={() => void feedback("not_for_me")}
              >
                Not for me
              </button>
              <button
                className="text-button"
                disabled={feedbackBusy}
                onClick={() => void feedback("already_know")}
              >
                I already know this
              </button>
            </div>
          )}
          {discovery?.agent && (
            <section className="experience-plan">
              <h3>Your introduction</h3>
              {discovery.agent.status === "planned" ? (
                <ol>
                  {discovery.agent.steps.map((step) => (
                    <li key={step.entity_id}>{step.instruction}</li>
                  ))}
                </ol>
              ) : (
                <p>
                  {discovery.agent.question ||
                    "The planner could not complete an introduction. The discoveries above are still available."}
                </p>
              )}
            </section>
          )}
          {error && (
            <p className="inline-error" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="muted" role="status">
              {notice}
            </p>
          )}
        </Dialog>
      )}
    </div>
  );
}
