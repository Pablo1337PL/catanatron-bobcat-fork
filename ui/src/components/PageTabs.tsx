import { Tab, Tabs } from "@mui/material";
import { Link, useLocation } from "react-router-dom";

import "./PageTabs.scss";

const PAGES = [
  { path: "/", label: "Play" },
  { path: "/analysis", label: "Analysis" },
] as const;

/** Top-level tabs of the start screen: set up a game, or analyze one. */
export default function PageTabs() {
  const { pathname } = useLocation();
  const current = PAGES.find((page) => page.path === pathname)?.path ?? false;
  return (
    <Tabs className="page-tabs" value={current} centered>
      {PAGES.map((page) => (
        <Tab
          key={page.path}
          value={page.path}
          label={page.label}
          component={Link}
          to={page.path}
        />
      ))}
    </Tabs>
  );
}
