import { photoUrl } from "../api.js";
import { categoryIcon, itemTitle, keptAtText, label, when } from "../lib/format.js";

// Every item is drawn as a luggage tag. side="found" gets a yellow stub, side="lost" a cobalt one.
export default function TagCard({ item, side = "found", aside, children, headingLevel = 3 }) {
  const Heading = `h${headingLevel}`;
  const title = itemTitle(item);
  const verb = side === "found" ? "Found" : "Last seen";
  const ago = item.time ? when(item.time) : "";
  const seen = item.location ? `${verb} at the ${label(item.location)}${ago ? `, ${ago}` : ""}` : `${verb} ${ago}`;
  return (
    <article className={`tag tag--${side}${aside ? " tag--aside" : ""}`}>
      <div className="tag__shape">
        <span className="tag__hole" aria-hidden="true" />
        <div className="tag__photo">
          {item.photo_url ? (
            <img src={photoUrl(item.photo_url)} alt={`Photo of the ${title.toLowerCase()}`} loading="lazy" />
          ) : (
            <span className="tag__nophoto">
              <span className="tag__icon" aria-hidden="true">{categoryIcon(item.category)}</span>
              No photo
            </span>
          )}
        </div>
        <div className="tag__body">
          <Heading className="tag__title">{title}</Heading>
          {item.description && <p className="tag__desc">{item.description}</p>}
          <p className="tag__facts">
            {(item.location || item.time) && <span>{seen}</span>}
            {side === "found" && item.kept_at && <span>{keptAtText(item.kept_at)}</span>}
          </p>
          {children}
        </div>
        {aside && <div className="tag__aside">{aside}</div>}
      </div>
    </article>
  );
}
