import type { User, Holding } from '@/types';

const STORAGE_KEY = 'eventsentry_user';
const STORAGE_KEY_LOGGED_IN = 'eventsentry_logged_in';

export const getUser = (): User | null => {
  const data = localStorage.getItem(STORAGE_KEY);
  if (!data) return null;
  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
};

export const setUser = (user: User): void => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  localStorage.setItem(STORAGE_KEY_LOGGED_IN, 'true');
};

export const isLoggedIn = (): boolean => {
  return localStorage.getItem(STORAGE_KEY_LOGGED_IN) === 'true' && getUser() !== null;
};

export const logout = (): void => {
  localStorage.removeItem(STORAGE_KEY_LOGGED_IN);
};

export const registerUser = (nickname: string): User => {
  const user: User = {
    id: 'user_' + Date.now(),
    nickname,
    holdings: [],
    subscriptions: {
      tickers: [],
      events: []
    },
    preferences: {
      risk_level: 'moderate',
      notification_enabled: true
    }
  };
  setUser(user);
  return user;
};

export const updateUser = (updates: Partial<User>): User | null => {
  const user = getUser();
  if (!user) return null;
  const updated = { ...user, ...updates };
  setUser(updated);
  return updated;
};

export const addHolding = (ticker: string, ticker_name: string, cost_price?: number): User | null => {
  const user = getUser();
  if (!user) return null;
  const exists = user.holdings.find(h => h.ticker === ticker);
  if (exists) return user;
  const holding: Holding = {
    id: 'hold_' + Date.now(),
    ticker,
    ticker_name,
    cost_price
  };
  user.holdings.push(holding);
  if (!user.subscriptions.tickers.includes(ticker)) {
    user.subscriptions.tickers.push(ticker);
  }
  setUser(user);
  return user;
};

export const removeHolding = (holdingId: string): User | null => {
  const user = getUser();
  if (!user) return null;
  user.holdings = user.holdings.filter(h => h.id !== holdingId);
  setUser(user);
  return user;
};

export const subscribeEvent = (eventId: string): User | null => {
  const user = getUser();
  if (!user) return null;
  if (!user.subscriptions.events.includes(eventId)) {
    user.subscriptions.events.push(eventId);
    setUser(user);
  }
  return user;
};

export const unsubscribeEvent = (eventId: string): User | null => {
  const user = getUser();
  if (!user) return null;
  user.subscriptions.events = user.subscriptions.events.filter(id => id !== eventId);
  setUser(user);
  return user;
};

export const subscribeTicker = (ticker: string): User | null => {
  const user = getUser();
  if (!user) return null;
  if (!user.subscriptions.tickers.includes(ticker)) {
    user.subscriptions.tickers.push(ticker);
    setUser(user);
  }
  return user;
};

export const updatePreferences = (prefs: Partial<User['preferences']>): User | null => {
  const user = getUser();
  if (!user) return null;
  user.preferences = { ...user.preferences, ...prefs };
  setUser(user);
  return user;
};
