import { useEffect } from "react";

const APP_NAME = "task-router";

/** Sets the browser tab title to "<title> | task-router" while the calling page is mounted. */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} | ${APP_NAME}`;
  }, [title]);
}
