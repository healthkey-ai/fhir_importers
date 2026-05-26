import css from "./mychart.css?inline";

let injected = false;

// Inject the module's scoped styles once into <head>. All selectors in
// mychart.css are scoped under `.mychart-root`, so this cannot leak into the
// host application's styles.
export function injectStyles(): void {
  if (injected) return;
  injected = true;

  const style = document.createElement("style");
  style.setAttribute("data-mf", "mychart-remote");
  style.textContent = css;
  document.head.appendChild(style);
}
