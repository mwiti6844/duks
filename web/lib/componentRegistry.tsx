// Maps allow-listed component types -> React components. Unknown types render
// nothing (the backend already schema-validates, this is defense in depth).
import AuctionCountdown, { AuctionProps } from "@/components/generative/AuctionCountdown";
import BidConfirmModal from "@/components/generative/BidConfirmModal";
import CarCard, { CarCardList, CarProps } from "@/components/generative/CarCard";
import ComparisonTable from "@/components/generative/ComparisonTable";
import FinancingCalculator from "@/components/generative/FinancingCalculator";
import FollowUpSuggestions from "@/components/generative/FollowUpSuggestions";
import KnowledgeAnswer from "@/components/generative/KnowledgeAnswer";
import ListingSummary from "@/components/generative/ListingSummary";
import PriceVerdictCard from "@/components/generative/PriceVerdictCard";

import type { FollowUpSuggestion, GenComponent, UIAction } from "./types";

export function renderComponent(
  c: GenComponent,
  key: string,
  onAction?: (label: string, action: UIAction) => void,
) {
  const p = c.props as never;
  switch (c.type) {
    case "car_card":
      return <CarCard key={key} onAction={onAction} car={(c.props as { car?: CarProps }).car ?? (c.props as unknown as CarProps)} />;
    case "car_card_list":
      return <CarCardList key={key} onAction={onAction} cars={(c.props as { cars: CarProps[] }).cars} />;
    case "comparison_table":
      return <ComparisonTable key={key} cars={(c.props as { cars: CarProps[] }).cars} />;
    case "price_verdict":
      return <PriceVerdictCard key={key} {...(p as Parameters<typeof PriceVerdictCard>[0])} />;
    case "financing_calculator":
      return <FinancingCalculator key={key} {...(p as Parameters<typeof FinancingCalculator>[0])} />;
    case "auction_countdown":
      return (
        <AuctionCountdown key={key} onAction={onAction} auctions={(c.props as { auctions: AuctionProps[] }).auctions} />
      );
    case "bid_confirm_modal":
      return <BidConfirmModal key={key} {...(p as Parameters<typeof BidConfirmModal>[0])} />;
    case "knowledge_answer":
      return <KnowledgeAnswer key={key} {...(p as Parameters<typeof KnowledgeAnswer>[0])} />;
    case "listing_summary":
      return <ListingSummary key={key} {...(p as Parameters<typeof ListingSummary>[0])} />;
    case "follow_up_suggestions":
      return (
        <FollowUpSuggestions
          key={key}
          onAction={onAction}
          suggestions={(c.props as { suggestions: FollowUpSuggestion[] }).suggestions}
        />
      );
    default:
      return null;
  }
}
