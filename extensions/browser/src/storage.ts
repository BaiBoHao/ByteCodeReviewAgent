const hasExtensionStorage =
  typeof chrome !== "undefined" && Boolean(chrome.storage?.local && chrome.storage?.session);

export async function loadLocal<T>(key: string, fallback: T): Promise<T> {
  if (hasExtensionStorage) {
    const values = await chrome.storage.local.get(key);
    return (values[key] as T | undefined) ?? fallback;
  }
  const value = window.localStorage.getItem(key);
  return value ? (JSON.parse(value) as T) : fallback;
}

export async function saveLocal<T>(key: string, value: T): Promise<void> {
  if (hasExtensionStorage) {
    await chrome.storage.local.set({ [key]: value });
  } else {
    window.localStorage.setItem(key, JSON.stringify(value));
  }
}

export async function loadSession(key: string): Promise<string | null> {
  if (hasExtensionStorage) {
    const values = await chrome.storage.session.get(key);
    return (values[key] as string | undefined) ?? null;
  }
  return window.sessionStorage.getItem(key);
}

export async function saveSession(key: string, value: string | null): Promise<void> {
  if (hasExtensionStorage) {
    if (value) await chrome.storage.session.set({ [key]: value });
    else await chrome.storage.session.remove(key);
  } else if (value) {
    window.sessionStorage.setItem(key, value);
  } else {
    window.sessionStorage.removeItem(key);
  }
}

export async function activeTabUrl(): Promise<string> {
  if (typeof chrome !== "undefined" && chrome.tabs) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab?.url || "";
  }
  return "https://github.com/BaiBoHao/ReviewProjectTest/pull/1";
}

export async function openTab(url: string): Promise<void> {
  if (typeof chrome !== "undefined" && chrome.tabs) {
    await chrome.tabs.create({ url });
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}
