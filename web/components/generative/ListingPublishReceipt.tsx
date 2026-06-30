export default function ListingPublishReceipt({
  listingId,
  created,
  operation,
}: {
  listingId: string;
  created: boolean;
  operation: "create" | "edit";
}) {
  const url = `/listings/${listingId}`;
  async function share() {
    const absolute = `${window.location.origin}${url}`;
    if (navigator.share) await navigator.share({ title: "CarDuka listing", url: absolute });
    else await navigator.clipboard.writeText(absolute);
  }
  async function startAnother() {
    const sessionId = localStorage.getItem("carduka_sid") || "";
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        message: "I want to sell another car",
        session_id: sessionId,
        action: { type: "start_journey", journey: "sell_car" },
      }),
    });
    await response.text();
    window.location.href = "/chat";
  }
  return (
    <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
      <p className="font-semibold">
        {operation === "edit" ? "Listing updated." : created ? "Listing published." : "Listing was already published."}
      </p>
      <p className="text-xs">Listing ID: {listingId}</p>
      <div className="mt-2 flex gap-2">
        <a href={url} className="rounded border border-emerald-300 px-2 py-1 text-xs">View listing</a>
        <a href={url} className="rounded border border-emerald-300 px-2 py-1 text-xs">Edit listing</a>
        <button onClick={share} className="rounded border border-emerald-300 px-2 py-1 text-xs">Share</button>
        <button onClick={startAnother} className="rounded border border-emerald-300 px-2 py-1 text-xs">Start another</button>
      </div>
    </div>
  );
}
