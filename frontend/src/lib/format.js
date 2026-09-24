const NAMES = { id_card: "ID card", other: "item" };

// Shown on a tag when the report has no photo.
const ICONS = {
  phone: "📱", laptop: "💻", tablet: "📱", charger: "🔌", earphones: "🎧", calculator: "🧮",
  bottle: "🍶", bag: "🎒", wallet: "👛", id_card: "🪪", keys: "🔑", clothing: "🧥",
  umbrella: "☂️", book: "📘", notebook: "📓", watch: "⌚", glasses: "👓", jewelry: "💍", other: "📦",
};
export const categoryIcon = (category) => ICONS[category] || ICONS.other;

export const label = (value) => (value ? value.replace(/_/g, " ") : "");

export const categoryName = (category) => NAMES[category] || label(category);

// "navy Milton bottle": for use mid-sentence. itemTitle() capitalizes it for headings.
export function itemName(item) {
  const colors = item.category === "id_card" ? "" : (item.colors || []).join(" and ");
  return [colors, item.brand, categoryName(item.category)].filter(Boolean).join(" ");
}

export function itemTitle(item) {
  const name = itemName(item);
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export function when(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  const mins = Math.round((Date.now() - date.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  return date.toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

// Value for <input type="datetime-local"> set to the current local time.
export function localNow() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export function keptAtText(keptAt) {
  if (!keptAt) return "";
  return keptAt === "With the finder" ? "The finder still has it" : `Waiting at the ${keptAt.toLowerCase()}`;
}
