Extract Domain 2 (WASH) structured data from the conversation.

Return ONLY a JSON object with exactly these keys:
{
  "water_source": string,
  "treats_water": boolean | null,
  "water_treatment_method": string,
  "toilet_type": string,
  "handwashing_station": string,
  "washes_after_toilet": string
}

Rules:
- Use null if the value is not provided or recorded as NA.
- "water_source" should be one of:
  "Piped water" | "Tube well / borehole" | "Protected well" | "Surface water (river/pond)" | "Other" | "Unknown"
- "water_treatment_method" should be one of:
  "Boil" | "Filter" | "Chlorine" | "Other" | "Unknown"
- "toilet_type" should be one of:
  "Flush toilet" | "Pit latrine" | "Shared toilet" | "No toilet (open defecation)" | "Other" | "Unknown"
- "handwashing_station" should be one of:
  "Yes, with soap and water" | "Water only" | "No designated place" | "Unknown"
- "washes_after_toilet" should be one of:
  "Always" | "Sometimes" | "Rarely" | "Never" | "Unknown"
- If the respondent describes a treatment method, set treats_water = true.
- If they explicitly say they do not treat water, set treats_water = false.

Return JSON only. No markdown. No extra text.