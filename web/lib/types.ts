export type ComponentType =
  | "car_card"
  | "car_card_list"
  | "comparison_table"
  | "financing_calculator"
  | "auction_countdown"
  | "bid_confirm_modal"
  | "price_verdict"
  | "knowledge_answer"
  | "listing_summary"
  | "follow_up_suggestions";

export type UIAction =
  | { type: "select_car"; entity_id: string }
  | { type: "compare_cars"; entity_ids: string[] }
  | { type: "price_verdict"; entity_id: string }
  | { type: "calculate_financing"; entity_id: string }
  | { type: "select_auction"; entity_id: string }
  | { type: "start_bid"; entity_id: string }
  | { type: "ask_knowledge"; topic: string }
  | { type: "browse_auctions" }
  | {
      type: "start_journey";
      journey:
        | "buy_car"
        | "sell_car"
        | "finance_car"
        | "trade_in"
        | "insurance"
        | "dealer_finance";
    };

export interface FollowUpSuggestion {
  id: string;
  label: string;
  action: UIAction;
}

export interface GenComponent {
  type: ComponentType;
  props: Record<string, unknown>;
}

export interface TraceEntry {
  kind: string;
  label: string;
  detail: Record<string, unknown>;
}

export interface ToolEvent {
  name: string;
  status: "started" | "completed";
  ms?: number;
  params?: Record<string, unknown>;
  detail?: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  components: GenComponent[];
  trace: TraceEntry[];
  tools: ToolEvent[];
  streaming?: boolean;
}

export interface DemoUser {
  id: string;
  username: string;
  full_name: string;
  location: string;
  profile_context?: string | null;
}
