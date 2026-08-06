"use client";

import { useEffect, useState } from "react";
import { BottomNav } from "@/components/bottom-nav";
import { Card } from "@/components/ui/card";
import { Search, FileText, Loader2, AlertTriangle, Trash2, CheckCircle2, CloudOff } from "lucide-react";
import { getCEUs, deleteCEU, formatDate, type CEU } from "@/lib/api";
import { ceuCategories, categoryDisplay } from "@/lib/mock-data";

export default function CEUsPage() {
  const [filter, setFilter] = useState<string>("All");
  const [search, setSearch] = useState("");
  const [ceus, setCEUs] = useState<CEU[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getCEUs();
        if (!cancelled) setCEUs(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load CEUs");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const [deleting, setDeleting] = useState<number | null>(null);

  const viewCertificate = (ceuId: number) => {
    const token = localStorage.getItem("breathe_token");
    const url = `/api/ceus/${ceuId}/certificate`;
    // Open in new tab with auth token as query param (simplest for inline viewing)
    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((res) => res.blob())
      .then((blob) => {
        const objUrl = URL.createObjectURL(blob);
        window.open(objUrl, "_blank");
        setTimeout(() => URL.revokeObjectURL(objUrl), 30000);
      })
      .catch(() => setError("Failed to load certificate"));
  };

  const handleDelete = async (id: number) => {
    setDeleting(id);
    try {
      await deleteCEU(id);
      setCEUs(ceus.filter((c) => c.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete");
    } finally {
      setDeleting(null);
    }
  };

  const totalCredits = ceus.reduce((a, c) => a + c.credits, 0);

  const filtered = ceus.filter((ceu) => {
    const displayCat = categoryDisplay[ceu.category] ?? ceu.category;
    const matchFilter = filter === "All" || displayCat === filter || ceu.category === filter;
    const matchSearch =
      ceu.title.toLowerCase().includes(search.toLowerCase()) ||
      ceu.provider.toLowerCase().includes(search.toLowerCase());
    return matchFilter && matchSearch;
  });

  if (loading) {
    return (
      <div className="page-enter min-h-screen pb-20">
        <div className="px-4 pt-8 pb-4">
          <h1 className="text-2xl font-bold text-text-primary">CEU Records</h1>
        </div>
        <div className="flex items-center justify-center pt-12">
          <Loader2 className="animate-spin text-primary" size={28} />
        </div>
        <BottomNav />
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-enter min-h-screen pb-20">
        <div className="px-4 pt-8 pb-4">
          <h1 className="text-2xl font-bold text-text-primary">CEU Records</h1>
        </div>
        <div className="px-4 mt-8 text-center">
          <AlertTriangle className="mx-auto text-danger mb-2" size={32} />
          <p className="text-danger font-medium">{error}</p>
        </div>
        <BottomNav />
      </div>
    );
  }

  return (
    <div className="page-enter min-h-screen pb-20">
      {/* Header */}
      <div className="px-4 pt-8 pb-4">
        <h1 className="text-2xl font-bold text-text-primary">CEU Records</h1>
        <p className="text-sm text-text-secondary mt-1">
          {ceus.length} total · {totalCredits} credits earned
        </p>
      </div>

      {/* Search */}
      <div className="px-4 mb-3">
        <div className="relative">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search CEUs..."
            className="w-full h-11 pl-10 pr-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary bg-white"
          />
        </div>
      </div>

      {/* Filter chips */}
      <div className="px-4 mb-4 flex gap-2 overflow-x-auto scrollbar-hide pb-1">
        {["All", ...ceuCategories].map((cat) => (
          <button
            key={cat}
            onClick={() => setFilter(cat)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-all ${
              filter === cat
                ? "bg-primary text-white"
                : "bg-white border border-gray-200 text-text-secondary hover:bg-gray-50"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="px-4 space-y-2">
        {filtered.length === 0 ? (
          <div className="text-center py-16">
            <div className="text-5xl mb-3">📭</div>
            <p className="text-text-secondary font-medium">No CEUs found</p>
            <p className="text-sm text-text-secondary mt-1">Try a different filter or search</p>
          </div>
        ) : (
          filtered.map((ceu) => {
            const displayCat = categoryDisplay[ceu.category] ?? ceu.category;
            return (
              <Card key={ceu.id} className="flex items-center gap-3 py-3">
                <button
                  onClick={ceu.certificate_path ? () => viewCertificate(ceu.id) : undefined}
                  className={`w-10 h-10 rounded-full bg-gradient-to-br from-primary/10 to-accent/10 flex items-center justify-center flex-shrink-0 ${ceu.certificate_path ? "cursor-pointer hover:from-primary/20 hover:to-accent/20" : ""}`}
                  title={ceu.certificate_path ? "View certificate" : "No certificate attached"}
                >
                  <FileText size={18} className="text-primary" />
                </button>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-text-primary truncate">{ceu.title}</p>
                  <p className="text-xs text-text-secondary">
                    {ceu.provider} · {ceu.credits} CEUs · {formatDate(ceu.completion_date)}
                  </p>
                </div>
                {/* CE Broker sync badge */}
                {ceu.cebroker_synced ? (
                  <span title={`Synced to CE Broker${ceu.cebroker_synced_at ? ` on ${formatDate(ceu.cebroker_synced_at)}` : ""}`}>
                    <CheckCircle2 size={16} className="text-success" />
                  </span>
                ) : (
                  <span title="Not synced to CE Broker">
                    <CloudOff size={16} className="text-gray-300" />
                  </span>
                )}
                <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-accent/10 text-accent whitespace-nowrap">
                  {displayCat}
                </span>
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(ceu.id); }}
                  disabled={deleting === ceu.id}
                  className="p-2 rounded-lg text-text-secondary hover:bg-danger/10 hover:text-danger transition-colors flex-shrink-0"
                  title="Delete CEU"
                >
                  {deleting === ceu.id ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Trash2 size={16} />
                  )}
                </button>
              </Card>
            );
          })
        )}
      </div>

      <BottomNav />
    </div>
  );
}