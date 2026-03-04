Extract Domain 3 (Temporal / Seasonal Factors) structured data from the full conversation.

Return ONLY JSON with exactly these keys:
{
  "recent_heatwave": boolean | null,
  "recent_heavy_rain": boolean | null,
  "recent_flood": boolean | null,
  "most_recent_event_date": string | null,
  "event_recency_days": integer | null,
  "community_diarrhoea_outbreak": boolean | null,
  "water_interruption": boolean | null,
  "extended_water_storage": boolean | null
}

Rules:
- Use null if not provided / recorded as NA.
- If respondent explicitly says "none" for Q1:
  set recent_heatwave=false, recent_heavy_rain=false, recent_flood=false.
- most_recent_event_date must be "YYYY-MM-DD" ONLY if explicitly provided; otherwise null.
- event_recency_days must be an integer 0–14 ONLY if explicitly provided; otherwise null.
- Map yes/no answers to true/false when clear; otherwise null.

Return JSON only. No markdown. No extra text.