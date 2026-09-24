// "Your reports" without accounts: remember report ids in this browser.
// Swap for campus login (SSO) before real use.
const KEY = "campus-lf:my-reports";

export function myReports() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || [];
  } catch {
    return [];
  }
}

export function rememberReport(id, kind) {
  const list = myReports().filter((r) => r.id !== id);
  list.unshift({ id, kind, at: Date.now() });
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, 20)));
  } catch {
    /* storage full or blocked: the app still works, the list just won't persist */
  }
}
