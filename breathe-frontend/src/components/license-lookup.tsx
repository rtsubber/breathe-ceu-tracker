"use client";

import { useState, useCallback } from "react";
import { Search, Loader2, CheckCircle2, AlertCircle, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  lookupLicense,
  type LicenseLookupResult,
} from "@/lib/api";

type LookupMode = "name" | "license";

type Props = {
  /** Pre-filled first name (from onboarding step 1) */
  initialFirstName?: string;
  /** Pre-filled last name (from onboarding step 1) */
  initialLastName?: string;
  /** State code for the license lookup (TX, IN, etc.) */
  state?: string;
  /** Called when user selects a result */
  onSelect: (result: LicenseLookupResult) => void;
  /** Optional: license type to search (default: RCP) */
  licenseType?: string;
};

export function LicenseLookup({
  initialFirstName = "",
  initialLastName = "",
  state = "TX",
  onSelect,
  licenseType = "RCP",
}: Props) {
  const [mode, setMode] = useState<LookupMode>("name");
  const [firstName, setFirstName] = useState(initialFirstName);
  const [lastName, setLastName] = useState(initialLastName);
  const [licenseNumber, setLicenseNumber] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<LicenseLookupResult[] | null>(null);
  const [searched, setSearched] = useState(false);

  const handleSearch = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResults(null);
    setSearched(false);

    try {
      const params: Record<string, string> = { license_type: licenseType };
      if (state) {
        params.state = state;
      }
      if (mode === "name") {
        if (!lastName.trim() && !firstName.trim()) {
          setError("Enter a name to search");
          setLoading(false);
          return;
        }
        params.first_name = firstName.trim();
        params.last_name = lastName.trim();
      } else {
        if (!licenseNumber.trim()) {
          setError("Enter a license number to search");
          setLoading(false);
          return;
        }
        params.license_number = licenseNumber.trim();
      }

      const response = await lookupLicense(params);
      setResults(response.results);
      setSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lookup failed");
    } finally {
      setLoading(false);
    }
  }, [mode, firstName, lastName, licenseNumber, licenseType, state]);

  const handleSelect = (result: LicenseLookupResult) => {
    onSelect(result);
    // Reset state after selection
    setResults(null);
    setSearched(false);
    setError(null);
  };

  const handleSwitchMode = (newMode: LookupMode) => {
    setMode(newMode);
    setResults(null);
    setSearched(false);
    setError(null);
  };

  return (
    <div className="space-y-4">
      {/* Mode toggle */}
      <div className="flex gap-2 p-1 bg-gray-100 rounded-button">
        <button
          type="button"
          onClick={() => handleSwitchMode("name")}
          className={`flex-1 h-9 rounded-button text-sm font-medium transition-all ${
            mode === "name"
              ? "bg-white text-primary shadow-sm"
              : "text-text-secondary hover:text-text-primary"
          }`}
        >
          Search by Name
        </button>
        <button
          type="button"
          onClick={() => handleSwitchMode("license")}
          className={`flex-1 h-9 rounded-button text-sm font-medium transition-all ${
            mode === "license"
              ? "bg-white text-primary shadow-sm"
              : "text-text-secondary hover:text-text-primary"
          }`}
        >
          Search by License #
        </button>
      </div>

      {/* Search inputs */}
      {mode === "name" ? (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-secondary">
              First Name
            </label>
            <div className="relative">
              <User
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary"
              />
              <input
                type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                placeholder="Ron"
                className="w-full h-11 pl-9 pr-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary text-sm"
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-text-secondary">
              Last Name
            </label>
            <div className="relative">
              <User
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary"
              />
              <input
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                placeholder="Sublett"
                className="w-full h-11 pl-9 pr-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary text-sm"
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-text-secondary">
            License Number
          </label>
          <input
            type="text"
            value={licenseNumber}
            onChange={(e) => setLicenseNumber(e.target.value)}
            placeholder="RCP00075612"
            className="w-full h-11 px-4 rounded-button border-2 border-gray-200 focus:border-primary focus:outline-none text-text-primary text-sm font-mono"
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
          <p className="text-xs text-text-secondary">
            Enter your license number (e.g. RCP00075612 for TX, 30010835A for IN)
          </p>
        </div>
      )}

      {/* Search button */}
      <Button
        type="button"
        variant="outline"
        size="md"
        className="w-full"
        onClick={handleSearch}
        disabled={loading}
      >
        {loading ? (
          <>
            <Loader2 size={18} className="mr-2 animate-spin" />
            Searching…
          </>
        ) : (
          <>
            <Search size={18} className="mr-2" />
            Look Up My License
          </>
        )}
      </Button>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-button text-sm text-red-700">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* No results */}
      {searched && results && results.length === 0 && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-button text-sm text-amber-800 text-center">
          <p className="font-medium">No license found</p>
          <p className="mt-1 text-amber-700">
            We couldn&apos;t find a matching license on the state licensing
            board database. Please enter your license info manually.
          </p>
        </div>
      )}

      {/* Results list */}
      {results && results.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-text-secondary">
            {results.length === 1
              ? "Found 1 match — tap to select:"
              : `Found ${results.length} matches — tap the right one:`}
          </p>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {results.map((result, idx) => (
              <button
                key={`${result.license_number}-${idx}`}
                type="button"
                onClick={() => handleSelect(result)}
                className="w-full text-left p-3 bg-white border-2 border-gray-200 rounded-button hover:border-primary hover:bg-primary/5 transition-all group"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-text-primary text-sm truncate">
                      {result.name}
                    </p>
                    <p className="text-xs text-text-secondary font-mono mt-0.5">
                      {result.license_number}
                    </p>
                    <p className="text-xs text-text-secondary mt-0.5">
                      {result.license_type_full || result.license_type}
                    </p>
                    {result.status && (
                      <span
                        className={`inline-flex items-center gap-1 mt-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${
                          result.status === "ACTIVE"
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        <CheckCircle2 size={12} />
                        {result.status}
                      </span>
                    )}
                  </div>
                  {result.expiry_date && (
                    <div className="text-right flex-shrink-0">
                      <p className="text-xs text-text-secondary">Expires</p>
                      <p className="text-sm font-medium text-text-primary">
                        {new Date(result.expiry_date).toLocaleDateString(
                          "en-US",
                          { month: "short", year: "numeric" },
                        )}
                      </p>
                    </div>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}