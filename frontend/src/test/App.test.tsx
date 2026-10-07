import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../App";
import {
  ApiError,
  createDiscovery,
  searchEntities,
  sendFeedback,
} from "../api";
import { previewPicks } from "../preview";
import { tagLabel, type Discovery, type Entity } from "../types";
vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  createDiscovery: vi.fn(),
  searchEntities: vi.fn(),
  sendFeedback: vi.fn(),
}));
const favourites: Entity[] = ["Bowie", "Radiohead", "Bjork"].map(
  (name, index) => ({
    id: `00000000-0000-4000-8000-00000000000${index}`,
    name,
    category: "artist",
    tags: [],
  }),
);
const result: Discovery = {
  id: "00000000-0000-4000-8000-000000000099",
  level: "experimental",
  data_mode: "live",
  items: previewPicks.map((pick, index) => ({
    ...pick,
    entity: {
      ...pick.entity,
      id: `00000000-0000-4000-8000-00000000001${index}`,
    },
    explanation: "A factual combined-interest connection.",
  })),
  coverage: [
    { category: "artist", status: "ok", exploration_supported: true },
    { category: "movie", status: "ok", exploration_supported: true },
    { category: "book", status: "ok", exploration_supported: true },
  ],
};
beforeEach(() => {
  vi.mocked(createDiscovery).mockReset().mockResolvedValue(result);
  vi.mocked(searchEntities)
    .mockReset()
    .mockImplementation(async (query) =>
      favourites.filter((entity) => entity.name === query),
    );
  vi.mocked(sendFeedback).mockReset().mockResolvedValue({ status: "saved" });
});
async function chooseInterests() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /Make it yours/ }));
  const input = screen.getByRole("textbox", { name: "Search your interests" });
  for (const favourite of favourites) {
    await user.type(input, favourite.name);
    await user.click(
      await screen.findByRole("button", { name: `${favourite.name} Music` }),
    );
  }
  return user;
}
async function goLive() {
  const user = await chooseInterests();
  await user.click(screen.getByRole("button", { name: /Build my system/ }));
  await screen.findByText("Live · Qloo");
  return user;
}
describe("orbital discovery", () => {
  it("shows readable Qloo tag labels without changing ordinary labels", () => {
    expect(tagLabel("urn:tag:genre:music:electronic")).toBe("Electronic");
    expect(tagLabel("urn:tag:genre:movie:science-fiction")).toBe(
      "Science fiction",
    );
    expect(tagLabel("Independent cinema")).toBe("Independent cinema");
  });
  it("labels the sample system and makes no provider calls on load", () => {
    render(<App />);
    expect(screen.getByText("Preview · sample system")).toBeVisible();
    expect(screen.getAllByRole("button", { name: /^Select / })).toHaveLength(6);
    expect(createDiscovery).not.toHaveBeenCalled();
    expect(searchEntities).not.toHaveBeenCalled();
  });
  it("selects a planet and changes the editorial panel", async () => {
    render(<App />);
    await userEvent.click(
      screen.getByRole("button", { name: "Select Melancholia, Film" }),
    );
    expect(
      screen.getByRole("heading", { level: 1, name: "Melancholia" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Select Melancholia, Film" }),
    ).toHaveAttribute("aria-pressed", "true");
  });
  it("keeps preview level changes local and opens a useful detail dialog", async () => {
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Wild" }));
    expect(screen.getByRole("button", { name: "Wild" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(createDiscovery).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /Explore this pick/ }));
    const dialog = screen.getByRole("dialog", { name: "Portishead" });
    expect(within(dialog).getByText("Music · Sample pick")).toBeVisible();
    expect(
      within(dialog).getByRole("link", { name: /Search the web/ }),
    ).toHaveAttribute("rel", "noopener noreferrer");
  });
  it("requires three catalog-confirmed interests, not the preview seeds", async () => {
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Make it yours/ }));
    expect(
      screen.getByRole("button", { name: /Build my system/ }),
    ).toBeDisabled();
    await user.type(
      screen.getByRole("textbox", { name: "Search your interests" }),
      "B",
    );
    expect(searchEntities).not.toHaveBeenCalled();
  });
  it("submits confirmed IDs and replaces the preview only on success", async () => {
    render(<App />);
    await goLive();
    expect(createDiscovery).toHaveBeenCalledWith(
      favourites,
      "experimental",
      "",
      expect.any(String),
      expect.any(AbortSignal),
    );
    expect(
      screen.queryByText("Preview · sample system"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("A factual combined-interest connection."),
    ).toBeVisible();
  });
  it("does not silently replace failed discovery with sample results and reuses retry key", async () => {
    vi.mocked(createDiscovery).mockRejectedValueOnce(new ApiError("network"));
    render(<App />);
    const user = await chooseInterests();
    await user.click(screen.getByRole("button", { name: /Build my system/ }));
    await screen.findByRole("alert");
    expect(screen.getByText("Preview · sample system")).toBeVisible();
    const firstKey = vi.mocked(createDiscovery).mock.calls[0][3];
    await user.click(screen.getByRole("button", { name: /Try again/ }));
    await screen.findByText("Live · Qloo");
    expect(vi.mocked(createDiscovery).mock.calls[1][3]).toBe(firstKey);
  });
  it("sends a new discovery request for a live exploration change", async () => {
    render(<App />);
    const user = await goLive();
    vi.mocked(createDiscovery).mockResolvedValueOnce({
      ...result,
      level: "wild",
    });
    await user.click(screen.getByRole("button", { name: "Wild" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Wild" })).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
    expect(vi.mocked(createDiscovery).mock.calls[1][1]).toBe("wild");
  });
  it("saves preview picks on device only and labels them in Saved", async () => {
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(sendFeedback).not.toHaveBeenCalled();
    await user.click(
      within(
        screen.getByRole("navigation", { name: "Your discoveries" }),
      ).getByRole("button", { name: /^Saved/ }),
    );
    expect(screen.getByText("Music · Sample")).toBeVisible();
  });
  it("saves live feedback only after backend acknowledgement", async () => {
    render(<App />);
    const user = await goLive();
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Saved to your discoveries.");
    expect(sendFeedback).toHaveBeenCalledWith(
      result.id,
      result.items[0].entity.id,
      "save",
    );
  });
  it("does not claim a failed live save succeeded", async () => {
    vi.mocked(sendFeedback).mockRejectedValueOnce(new ApiError("expired"));
    render(<App />);
    const user = await goLive();
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    expect(localStorage.getItem("tasteshift.saved.v1")).toBeNull();
  });
  it("keeps an empty live result empty instead of filling it with examples", async () => {
    vi.mocked(createDiscovery).mockResolvedValueOnce({ ...result, items: [] });
    render(<App />);
    await goLive();
    expect(screen.getByText("No discoveries this time.")).toBeVisible();
    expect(screen.queryAllByRole("button", { name: /^Select / })).toHaveLength(
      0,
    );
  });
  it("shows limited exploration and planner fallback honestly", async () => {
    vi.mocked(createDiscovery).mockResolvedValueOnce({
      ...result,
      coverage: [
        { category: "book", status: "ok", exploration_supported: false },
      ],
      agent: {
        status: "needs_clarification",
        question: "Would you prefer a film or a book?",
        steps: [],
      },
    });
    render(<App />);
    const user = await goLive();
    expect(screen.getByText(/limited exploration data/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: /Explore this pick/ }));
    expect(
      screen.getByText("Would you prefer a film or a book?"),
    ).toBeVisible();
  });
  it("pauses motion and ignores corrupt saved storage", async () => {
    localStorage.setItem("tasteshift.saved.v1", JSON.stringify([{ pick: {} }]));
    const { container } = render(<App />);
    await userEvent.click(
      screen.getByRole("button", { name: "Pause animations" }),
    );
    expect(container.querySelector(".app-shell")).toHaveAttribute(
      "data-motion-off",
      "true",
    );
  });
  it("respects system reduced motion from the first render", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    });
    const { container } = render(<App />);
    expect(container.querySelector(".app-shell")).toHaveAttribute(
      "data-motion-off",
      "true",
    );
    expect(
      screen.getByRole("button", { name: "Pause animations" }),
    ).toBeDisabled();
  });
  it("ignores an old search response after a newer query", async () => {
    let finishOld!: (items: Entity[]) => void;
    vi.mocked(searchEntities).mockImplementation((query) =>
      query === "Bowie"
        ? new Promise<Entity[]>((resolve) => {
            finishOld = resolve;
          })
        : Promise.resolve([favourites[1]]),
    );
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Make it yours/ }));
    const input = screen.getByRole("textbox", {
      name: "Search your interests",
    });
    await user.type(input, "Bowie");
    await waitFor(() => expect(searchEntities).toHaveBeenCalled());
    await user.clear(input);
    await user.type(input, "Radiohead");
    await screen.findByRole("button", { name: "Radiohead Music" });
    finishOld([favourites[0]]);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Radiohead Music" }),
      ).toBeVisible(),
    );
    expect(
      screen.queryByRole("button", { name: "Bowie Music" }),
    ).not.toBeInTheDocument();
  });
});
