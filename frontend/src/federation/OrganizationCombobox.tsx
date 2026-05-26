import { useEffect, useMemo, useRef, useState } from "react";
import type { Organization } from "./types";

interface Props {
  organizations: Organization[];
  value: Organization | null;
  onChange: (org: Organization | null) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function OrganizationCombobox({
  organizations,
  value,
  onChange,
  disabled,
  placeholder,
}: Props) {
  const [query, setQuery] = useState<string>(value?.title ?? "");
  const [open, setOpen] = useState<boolean>(false);
  const [highlight, setHighlight] = useState<number>(0);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setQuery(value?.title ?? "");
  }, [value]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const filtered = useMemo<Organization[]>(() => {
    const q = query.trim().toLowerCase();
    if (!q) return organizations;
    return organizations.filter(
      (o) =>
        o.title.toLowerCase().includes(q) || o.alias.toLowerCase().includes(q),
    );
  }, [organizations, query]);

  useEffect(() => {
    if (highlight >= filtered.length) setHighlight(Math.max(0, filtered.length - 1));
  }, [filtered.length, highlight]);

  const select = (org: Organization) => {
    onChange(org);
    setQuery(org.title);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHighlight((h) => Math.min(h + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      if (open && filtered[highlight]) {
        e.preventDefault();
        select(filtered[highlight]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="combobox" ref={rootRef}>
      <input
        type="text"
        className="combobox-input"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setHighlight(0);
          if (value && e.target.value !== value.title) onChange(null);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        role="combobox"
        aria-expanded={open}
        aria-controls="mychart-combobox-list"
        aria-autocomplete="list"
        autoComplete="off"
        spellCheck={false}
      />
      {open && filtered.length > 0 && (
        <ul id="mychart-combobox-list" role="listbox" className="combobox-list">
          {filtered.map((o, i) => (
            <li
              key={o.alias}
              role="option"
              aria-selected={highlight === i}
              className={`combobox-option${highlight === i ? " highlighted" : ""}`}
              onMouseDown={(e) => {
                e.preventDefault();
                select(o);
              }}
              onMouseEnter={() => setHighlight(i)}
            >
              <div className="combobox-option-title">{o.title}</div>
              <div className="combobox-option-alias">{o.alias}</div>
            </li>
          ))}
        </ul>
      )}
      {open && filtered.length === 0 && query.trim() && (
        <div className="combobox-empty">No matches</div>
      )}
    </div>
  );
}
