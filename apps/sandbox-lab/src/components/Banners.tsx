// D-088 S-02 Banners.
import type { BannerEntry } from "../types/sandbox";

export interface BannersProps {
  banners: BannerEntry[];
  onDismiss?: (id: string) => void;
}

export function Banners({ banners, onDismiss }: BannersProps) {
  if (banners.length === 0) return null;
  return (
    <div className="banner-stack">
      {banners.map((b) => (
        <div key={b.id} className={`banner ${b.level}`}>
          <span className="bico">
            {b.level === "danger" ? "!" : b.level === "review" ? "⏱" : "!"}
          </span>
          <div className="b-msg">
            <strong>{b.title}</strong>
            <span className="b-detail">{b.detail}</span>
          </div>
          {b.dismissable && onDismiss && (
            <button className="b-fold" onClick={() => onDismiss(b.id)}>
              收起
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
