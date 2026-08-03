/**
 * Static UI constants only. All user/CEU/credential data comes from the API
 * via lib/api.ts. This file is kept for shared constants used by forms and
 * filters.
 */

export const usStates = [
  "Texas", "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
  "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois",
  "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
  "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana",
  "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York",
  "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
  "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Utah", "Vermont",
  "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
];

export const ceuCategories = [
  "Critical Care",
  "Neonatal",
  "Emergency",
  "Ethics",
  "Diagnostics",
  "Pulmonary Rehab",
  "Sleep Medicine",
  "Pediatrics",
  "General",
];

/** Canonical category mapping for display. */
export const categoryDisplay: Record<string, string> = {
  clinical: "Critical Care",
  neonatal: "Neonatal",
  emergency: "Emergency",
  ethics: "Ethics",
  diagnostics: "Diagnostics",
  pulmonary_rehab: "Pulmonary Rehab",
  sleep: "Sleep Medicine",
  pediatrics: "Pediatrics",
  general: "General",
};