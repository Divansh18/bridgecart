/** Assistant and upstream text is untrusted. Only absolute web and mail links are clickable. */
export function safeMarkdownUrl(value: string): string {
  try {
    const url = new URL(value.trim());
    if (!["http:", "https:", "mailto:"].includes(url.protocol)) return "";
    if (url.username || url.password) return "";
    return url.href;
  } catch {
    return "";
  }
}
