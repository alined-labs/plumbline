/** Eight hex digits a reader can quote. getRandomValues, unlike randomUUID, also works on a
 * plain-HTTP origin such as a LAN address in development. */
export function localErrorId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(4)), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}
