export type Role = 'customer' | 'staff' | 'manager';

export interface Prefs {
  temperature?: 'hot' | 'iced' | 'any' | null;
  sweetness?: number | null;
  milk?: string | null;
  caffeine?: string | null;
  flavours?: string[];
  diet?: 'any' | 'veg' | 'vegan';
  avoid?: string[];
  dislikes?: string[];
}

export interface Me {
  uid: string;
  email: string;
  role: Role;
  roleChanged: boolean;
  displayName: string;
  photoURL?: string | null;
  prefs: Prefs;
  onboarded: boolean;
  usuals: { itemId: string; name: string; modifiers: Record<string, string>; modifierLabels: string[]; count: number }[];
}

export interface ModifierGroup {
  label: string;
  options: { id: string; label: string; delta: number }[];
}

export interface MenuItem {
  id: string;
  name: string;
  category: string;
  price: number;
  description: string;
  tags: string[];
  dietary: string[];
  modifiers: string[];
  available: boolean;
  prepSec: number;
}

export interface Menu {
  categories: { id: string; label: string }[];
  modifiers: Record<string, ModifierGroup>;
  items: MenuItem[];
}

export interface CartLine {
  lineId: string;
  itemId: string;
  name: string;
  qty: number;
  modifiers: Record<string, string>;
  modifierLabels: string[];
  unitPrice: number;
  lineTotal: number;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  at: string;
  actions?: string[];
}

export interface Session {
  cafeId: string;
  messages: ChatMessage[];
  cart: CartLine[];
  total: number;
  pickupAt: string | null;
}

export type OrderStatus = 'scheduled' | 'placed' | 'in_progress' | 'ready' | 'collected' | 'cancelled';

export interface Eta {
  readyAt: string;
  lowAt: string;
  highAt: string;
  queuePosition: number | null;
  updatedAt: string;
  releaseAt?: string;
}

export interface Order {
  id: string;
  uid: string;
  customerName: string;
  cafeId: string;
  items: (CartLine & { prepSec: number })[];
  total: number;
  notes: string;
  status: OrderStatus;
  pickupCode: string;
  source: string;
  dineIn?: boolean;
  tableId?: string | null;
  tableLabel?: string | null;
  createdAt: string;
  placedAt: string | null;
  startedAt?: string;
  readyAt?: string;
  scheduledFor: string | null;
  payment: { method: 'upi' | 'card' | 'counter'; status: 'paid' | 'pending' | 'refunded'; txnId: string | null };
  eta?: Eta;
}

export interface LiveStats {
  activeOrders: number;
  queuedItems: number;
  scheduledOrders: number;
  currentWaitSec: number;
  baristasOnShift: number;
  etaAbsErrorEwmaSec?: number;
  updatedAt: string;
}

export interface Recommendation {
  item: MenuItem;
  score: number;
  reason: string;
  suggestedModifiers: Record<string, string>;
}

export interface Slot {
  start: string;
  expectedWaitSec: number;
  orders: number;
  level: 'quiet' | 'moderate' | 'busy';
}

export interface PublicProfile {
  uid: string;
  firstName: string;
  bio: string;
  interests: string[];
  openTo: string[];
}

export interface Person extends PublicProfile {
  mood: string;
  sharedInterests: string[];
  matchScore: number;
  checkedInAt: string;
}

export interface Spark {
  id: string;
  fromUid: string;
  toUid: string;
  cafeId: string;
  note: string;
  from: PublicProfile;
  to: PublicProfile;
  sharedInterests: string[];
  status: 'pending' | 'accepted' | 'declined' | 'expired';
  connectionId?: string;
  createdAt: Date;
  expiresAt: Date;
}

export interface Connection {
  id: string;
  members: string[];
  profiles: Record<string, PublicProfile>;
  cafeName: string;
  openedAt: Date;
  windowEndsAt: Date;
  status: 'open' | 'met' | 'expired' | 'closed';
  meetup: { at: Date; proposedBy: string; confirmedBy: string[] } | null;
  metBy?: string[];
  icebreakers: string[];
  lastMessage?: string;
}
