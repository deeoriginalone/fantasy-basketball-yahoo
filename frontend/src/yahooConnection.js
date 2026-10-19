export function sanitizeYahooDraftUrl(value) {
  const url = new URL(value);
  if (url.protocol !== "https:" || url.hostname !== "basketball.fantasysports.yahoo.com"
      || (url.port && url.port !== "443") || url.username || url.password
      || !/^\/draftclient\/nba\/[0-9]{1,20}\/[0-9]{1,10}\/?$/.test(url.pathname)) {
    throw new Error("Paste a Yahoo Basketball draft-room URL, not a lobby URL.");
  }
  return url.pathname.replace(/\/$/, "");
}
