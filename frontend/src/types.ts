export type Category = "artist" | "movie" | "book";
export type Level = "safe" | "curious" | "experimental" | "wild";
export type Feedback = "save" | "not_for_me" | "already_know";
export interface Entity {
  id: string;
  name: string;
  category: Category;
  description?: string | null;
  image_url?: string | null;
  website_url?: string | null;
  tags: string[];
}
export interface Pick {
  entity: Entity;
  explanation: string;
  shared_tags: string[];
}
export interface Discovery {
  id: string;
  level: Level;
  items: Pick[];
  data_mode: string;
  coverage: {
    category: Category;
    status: string;
    exploration_supported: boolean;
  }[];
  agent?: {
    status: string;
    question?: string | null;
    steps: { entity_id: string; action: string; instruction: string }[];
  } | null;
}
export interface SavedPick {
  pick: Pick;
  discoveryId: string | null;
  preview: boolean;
}
export const LEVELS: Level[] = ["safe", "curious", "experimental", "wild"];
export const categoryLabel: Record<Category, string> = {
  artist: "Music",
  movie: "Film",
  book: "Book",
};
export function tagLabel(tag: string): string {
  if (!tag.startsWith("urn:tag:")) return tag;
  const label = tag.split(":").at(-1)?.replace(/[_-]+/g, " ") || tag;
  return label.charAt(0).toUpperCase() + label.slice(1);
}
