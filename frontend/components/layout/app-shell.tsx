"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { fetchApi } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Freshness } from "@/types/dashboard";

const links = [
  { href: "/overview", label: "Overview" },
  { href: "/correlation", label: "Correlation" },
  { href: "/finder", label: "Finder" },
  { href: "/risk", label: "Predictive Risk" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [progress, setProgress] = useState(0);
  const [tooltip, setTooltip] = useState<{
    text: string;
    x: number;
    y: number;
    placement: "top" | "bottom";
  } | null>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const freshness = useQuery({
    queryKey: ["data-freshness"],
    queryFn: ({ signal }) => fetchApi<Freshness>("/data-freshness", {}, signal),
  });
  const freshnessLabel = freshness.isLoading
    ? "Checking warehouse snapshot..."
    : freshness.data?.latest_inspection_date
      ? `Warehouse snapshot through ${formatDate(freshness.data.latest_inspection_date)}`
      : "Warehouse snapshot unavailable";

  useEffect(() => {
    const updateProgress = () => {
      const distance =
        document.documentElement.scrollHeight - window.innerHeight;
      setProgress(distance > 0 ? (window.scrollY / distance) * 100 : 0);
    };
    updateProgress();
    window.addEventListener("scroll", updateProgress, { passive: true });
    window.addEventListener("resize", updateProgress);
    return () => {
      window.removeEventListener("scroll", updateProgress);
      window.removeEventListener("resize", updateProgress);
    };
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);

  useEffect(() => {
    const enhance = (root: ParentNode) => {
      const titled =
        root instanceof HTMLElement && root.hasAttribute("title")
          ? [root]
          : Array.from(root.querySelectorAll<HTMLElement>("[title]"));
      titled.forEach((element) => {
        const text = element.getAttribute("title");
        if (!text) return;
        const target = element.matches(".stacked-bar")
          ? (element.closest<HTMLElement>(".distribution-row") ?? element)
          : element;
        target.dataset.tooltip = text;
        if (target.classList.contains("data-status"))
          target.dataset.tooltipPlacement = "bottom";
        if (!target.closest("button, a, [tabindex]") && target.tabIndex < 0)
          target.tabIndex = 0;
        element.removeAttribute("title");
      });
    };

    const show = (target: HTMLElement) => {
      const text = target.dataset.tooltip;
      if (!text) return;
      const rect = target.getBoundingClientRect();
      const placement =
        target.dataset.tooltipPlacement === "bottom" || rect.top < 90
          ? "bottom"
          : "top";
      const x = Math.min(
        Math.max(rect.left + rect.width / 2, 170),
        window.innerWidth - 170,
      );
      const y = placement === "top" ? rect.top - 10 : rect.bottom + 10;
      setTooltip({ text, x, y, placement });
    };
    const findTarget = (node: EventTarget | null) =>
      node instanceof Element
        ? node.closest<HTMLElement>("[data-tooltip]")
        : null;
    const onPointerOver = (event: PointerEvent) => {
      const target = findTarget(event.target);
      if (target) show(target);
    };
    const onPointerOut = (event: PointerEvent) => {
      const target = findTarget(event.target);
      if (target && !target.contains(event.relatedTarget as Node | null))
        setTooltip(null);
    };
    const onFocusIn = (event: FocusEvent) => {
      const target = findTarget(event.target);
      if (target) show(target);
    };
    const onFocusOut = (event: FocusEvent) => {
      if (findTarget(event.target)) setTooltip(null);
    };
    const hide = () => setTooltip(null);

    enhance(document);
    const observer = new MutationObserver((mutations) =>
      mutations.forEach((mutation) => {
        if (mutation.type === "attributes")
          enhance(mutation.target as HTMLElement);
        mutation.addedNodes.forEach((node) => {
          if (node instanceof HTMLElement) enhance(node);
        });
      }),
    );
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["title"],
    });
    document.addEventListener("pointerover", onPointerOver);
    document.addEventListener("pointerout", onPointerOut);
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);
    window.addEventListener("scroll", hide, { passive: true });
    window.addEventListener("resize", hide);
    return () => {
      observer.disconnect();
      document.removeEventListener("pointerover", onPointerOver);
      document.removeEventListener("pointerout", onPointerOut);
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
      window.removeEventListener("scroll", hide);
      window.removeEventListener("resize", hide);
    };
  }, []);

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <div className="mesh-background" aria-hidden="true" />
      <div
        className="reading-progress"
        style={{ transform: `scaleX(${progress / 100})` }}
        aria-hidden="true"
      />
      <header className="app-header">
        <div className="header-inner">
          <Link className="brand" href="/" aria-label="SafeEats NYC home">
            <span className="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="m4 7 8-4 8 4-8 4-8-4Z" />
                <path d="m4 11 8 4 8-4" />
                <path d="m4 15 8 4 8-4" />
              </svg>
            </span>
            <span className="brand-copy">
              <strong>SafeEats NYC</strong>
              <small>Restaurant Safety Intelligence</small>
            </span>
          </Link>
          <button
            ref={menuButton}
            className="menu-button"
            type="button"
            aria-expanded={menuOpen}
            aria-controls="primary-navigation"
            onClick={() => setMenuOpen((current) => !current)}
          >
            <span className="sr-only">Toggle navigation</span>
            <span aria-hidden="true">{menuOpen ? "Close" : "Menu"}</span>
          </button>
          <nav
            id="primary-navigation"
            className={`primary-nav ${menuOpen ? "is-open" : ""}`}
            aria-label="Primary navigation"
          >
            {links.map((link) => {
              const active = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={active ? "active" : undefined}
                  aria-current={active ? "page" : undefined}
                  onClick={() => setMenuOpen(false)}
                >
                  {link.label}
                </Link>
              );
            })}
            <span className="mobile-data-status">
              <span aria-hidden="true" />
              {freshnessLabel}
            </span>
          </nav>
          <span
            className="data-status"
            title={
              freshness.data
                ? `${freshness.data.refresh_description} Latest 311 complaint: ${formatDate(freshness.data.latest_complaint_date)}. ML scoring: ${formatDate(freshness.data.latest_ml_scoring_timestamp)}.`
                : undefined
            }
          >
            <span aria-hidden="true" />
            {freshnessLabel}
          </span>
        </div>
      </header>
      {children}
      {tooltip && (
        <div
          className={`global-tooltip global-tooltip-${tooltip.placement}`}
          role="tooltip"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.text}
        </div>
      )}
      <footer className="app-footer">
        <div className="footer-inner">
          <p>
            <strong>SafeEats NYC</strong> · NYC restaurant safety, made clearer.
          </p>
          <nav aria-label="Footer navigation">
            {links.map((link) => (
              <Link key={link.href} href={link.href}>
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
      </footer>
    </>
  );
}
