import css from "./healthex.css?inline";

let injected = false;

// Inject the module's scoped styles once into <head>. All selectors in
// healthex.css are scoped under `.healthex-root`, so this cannot leak into
// the host application's styles.
export function injectHealthExStyles(): void {
  if (injected) return;
  injected = true;

  const style = document.createElement("style");
  style.setAttribute("data-mf", "healthex-remote");
  style.textContent = css;
  document.head.appendChild(style);
}
