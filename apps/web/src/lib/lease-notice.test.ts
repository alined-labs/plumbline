import { markNoticeSeen, noticeSeen } from "./lease-notice";

afterEach(() => {
  window.sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("the redaction notice", () => {
  it("is unseen until it is marked, and then stays seen for the session", () => {
    expect(noticeSeen()).toBe(false);
    markNoticeSeen();
    expect(noticeSeen()).toBe(true);
  });

  it("is shown every time when storage is refused", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    expect(() => markNoticeSeen()).not.toThrow();
    expect(noticeSeen()).toBe(false);
  });
});
