import type { Entity, Pick } from "./types";
const entity = (
  id: string,
  name: string,
  category: Entity["category"],
): Entity => ({ id: `sample-${id}`, name, category, tags: [] });
export const previewSeeds = [
  entity("bowie", "David Bowie", "artist"),
  entity("radiohead", "Radiohead", "artist"),
  entity("bjork", "Björk", "artist"),
];
export const previewPicks: Pick[] = [
  entity("portishead", "Portishead", "artist"),
  entity("kate-bush", "Kate Bush", "artist"),
  entity("melancholia", "Melancholia", "movie"),
  entity("the-fall", "The Fall", "movie"),
  entity("walrus", "I Met the Walrus", "book"),
  entity("lennon", "Lennon: The Life", "book"),
].map((entity) => ({
  entity,
  explanation:
    "An illustrative pick for this sample system. Make it yours to get a factual explanation from Qloo.",
  shared_tags: [],
}));
