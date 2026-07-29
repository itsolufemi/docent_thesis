export type TurnLabel = "complete" | "incomplete";

export type RecordingPrompt = {
  id: string;
  order: number;
  text: string;
  label: TurnLabel;
  category: string;
  categoryLabel: string;
  delivery: string;
};

const completePrompts: Omit<RecordingPrompt, "order" | "label">[] = [
  {
    id: "human_01_direct_request",
    text: "Tell me about The Arab Tent.",
    category: "complete_request",
    categoryLabel: "Direct request",
    delivery: "Say this naturally and finish with clear finality.",
  },
  {
    id: "human_02_wh_question",
    text: "Who painted it?",
    category: "complete_question",
    categoryLabel: "Question",
    delivery: "Ask it as a genuine, self-contained question.",
  },
  {
    id: "human_03_tour_command",
    text: "Give me a highlights tour.",
    category: "complete_command",
    categoryLabel: "Command",
    delivery: "Use your normal voice; do not over-emphasise the ending.",
  },
  {
    id: "human_04_short_affirmation",
    text: "Yes.",
    category: "short_answer",
    categoryLabel: "Short answer",
    delivery: "Respond as if you have just accepted an offered choice.",
  },
  {
    id: "human_05_contextual_answer",
    text: "Its history.",
    category: "contextual_answer",
    categoryLabel: "Contextual answer",
    delivery:
      "Imagine you were asked: “Would you like its history or composition?”",
  },
  {
    id: "human_06_declarative",
    text: "The Arab Tent is remarkable.",
    category: "complete_declarative",
    categoryLabel: "Statement",
    delivery: "Make this a complete observation, not the start of a list.",
  },
  {
    id: "human_07_polite_completion",
    text: "Please continue.",
    category: "complete_command",
    categoryLabel: "Command",
    delivery: "Say it politely, as you would to the museum guide.",
  },
  {
    id: "human_08_short_rejection",
    text: "No, thank you.",
    category: "short_answer",
    categoryLabel: "Short answer",
    delivery: "Use natural conversational finality.",
  },
  {
    id: "human_09_next_question",
    text: "What should I look at next?",
    category: "complete_question",
    categoryLabel: "Question",
    delivery: "Ask this as one complete question.",
  },
  {
    id: "human_10_more_request",
    text: "I'd like to hear more.",
    category: "complete_request",
    categoryLabel: "Direct request",
    delivery: "Use your ordinary speaking pace.",
  },
  {
    id: "human_11_composition_request",
    text: "Tell me about the painting's composition.",
    category: "complete_request",
    categoryLabel: "Direct request",
    delivery: "Finish the request cleanly.",
  },
  {
    id: "human_12_yes_no_question",
    text: "Was it painted in France?",
    category: "complete_question",
    categoryLabel: "Question",
    delivery: "Ask it naturally, without adding another thought.",
  },
  {
    id: "human_13_backchannel",
    text: "That makes sense.",
    category: "backchannel",
    categoryLabel: "Backchannel",
    delivery: "Say this as a complete acknowledgement.",
  },
  {
    id: "human_14_move_command",
    text: "Let's move to the next room.",
    category: "complete_command",
    categoryLabel: "Command",
    delivery: "Use decisive but conversational finality.",
  },
  {
    id: "human_15_repeat_request",
    text: "Could you repeat that?",
    category: "complete_question",
    categoryLabel: "Question",
    delivery: "Ask it as a complete repair request.",
  },
  {
    id: "human_16_observation",
    text: "The colours are beautiful.",
    category: "complete_declarative",
    categoryLabel: "Statement",
    delivery: "Make a complete observation.",
  },
  {
    id: "human_17_hesitation_request",
    text: "Could you tell me about — The Arab Tent?",
    category: "hesitation_complete",
    categoryLabel: "Mid-turn pause",
    delivery:
      "Pause naturally for about half a second at the dash, then finish the question.",
  },
  {
    id: "human_18_hesitation_statement",
    text: "I think that — the painting is beautiful.",
    category: "hesitation_complete",
    categoryLabel: "Mid-turn pause",
    delivery:
      "Pause naturally for about half a second at the dash, then complete the sentence.",
  },
  {
    id: "human_19_two_clause_pause",
    text: "The Arab Tent is remarkable. — Its interior is richly decorated.",
    category: "hesitation_complete",
    categoryLabel: "Clause boundary",
    delivery:
      "Pause for about half a second at the dash, then say the second sentence.",
  },
  {
    id: "human_20_hesitant_question",
    text: "Before we continue, — what should I look at next?",
    category: "hesitation_complete",
    categoryLabel: "Mid-turn pause",
    delivery:
      "Pause briefly at the dash, as if gathering your thought, then finish.",
  },
];

const incompletePrompts: Omit<RecordingPrompt, "order" | "label">[] = [
  {
    id: "human_21_trailing_object",
    text: "Could you tell me about…",
    category: "trailing_object",
    categoryLabel: "Missing object",
    delivery:
      "Stop as though you are about to name the object. Do not say “dot dot dot”.",
  },
  {
    id: "human_22_trailing_because",
    text: "I wanted to ask because…",
    category: "trailing_conjunction",
    categoryLabel: "Trailing conjunction",
    delivery:
      "Leave the reason unsaid. Keep the vocal sense that more is coming.",
  },
  {
    id: "human_23_trailing_determiner",
    text: "Tell me about the…",
    category: "trailing_determiner",
    categoryLabel: "Trailing determiner",
    delivery: "Stop before naming the thing you want to hear about.",
  },
  {
    id: "human_24_trailing_copula",
    text: "I think the painting is…",
    category: "trailing_copula",
    categoryLabel: "Unfinished description",
    delivery: "Stop before supplying the description.",
  },
  {
    id: "human_25_trailing_and",
    text: "And what about…",
    category: "trailing_conjunction",
    categoryLabel: "Trailing conjunction",
    delivery: "Sound as though the subject is about to follow.",
  },
  {
    id: "human_26_conditional_clause",
    text: "If we move to the next room…",
    category: "subordinate_clause",
    categoryLabel: "Conditional clause",
    delivery: "Do not provide the result of the condition.",
  },
  {
    id: "human_27_relative_clause",
    text: "The artist who painted it…",
    category: "relative_clause",
    categoryLabel: "Relative clause",
    delivery: "Stop before explaining what the artist did or who they were.",
  },
  {
    id: "human_28_question_stem",
    text: "Could you explain how…",
    category: "question_stem",
    categoryLabel: "Question stem",
    delivery: "Leave the process or event unspecified.",
  },
  {
    id: "human_29_observation_stem",
    text: "One thing I noticed was…",
    category: "trailing_copula",
    categoryLabel: "Unfinished observation",
    delivery: "Stop before saying what you noticed.",
  },
  {
    id: "human_30_comparison_stem",
    text: "It seems as though…",
    category: "subordinate_clause",
    categoryLabel: "Subordinate clause",
    delivery: "Leave the comparison or conclusion unfinished.",
  },
  {
    id: "human_31_before_clause",
    text: "Before we continue…",
    category: "subordinate_clause",
    categoryLabel: "Subordinate clause",
    delivery: "Sound as though a request is about to follow.",
  },
  {
    id: "human_32_whether_clause",
    text: "I was wondering whether…",
    category: "question_stem",
    categoryLabel: "Question stem",
    delivery: "Stop before stating the alternatives or question.",
  },
  {
    id: "human_33_reason_clause",
    text: "The reason I asked is…",
    category: "trailing_copula",
    categoryLabel: "Unfinished explanation",
    delivery: "Do not supply the reason.",
  },
  {
    id: "human_34_when_clause",
    text: "When the collection first opened…",
    category: "subordinate_clause",
    categoryLabel: "Time clause",
    delivery: "Stop before saying what happened.",
  },
  {
    id: "human_35_knowledge_stem",
    text: "What I really want to know is…",
    category: "trailing_copula",
    categoryLabel: "Question stem",
    delivery: "Leave the desired information unspecified.",
  },
  {
    id: "human_36_although_clause",
    text: "Although the painting looks simple…",
    category: "subordinate_clause",
    categoryLabel: "Contrast clause",
    delivery: "Stop before completing the contrast.",
  },
  {
    id: "human_37_about_stem",
    text: "Is there anything else about…",
    category: "trailing_object",
    categoryLabel: "Missing object",
    delivery: "Stop before naming the subject.",
  },
  {
    id: "human_38_if_intention",
    text: "So if the artist intended to…",
    category: "subordinate_clause",
    categoryLabel: "Conditional clause",
    delivery: "Leave both the intended action and its consequence unfinished.",
  },
  {
    id: "human_39_comparison_clause",
    text: "Compared with the other works…",
    category: "subordinate_clause",
    categoryLabel: "Comparison clause",
    delivery: "Stop before making the comparison.",
  },
  {
    id: "human_40_interest_clause",
    text: "The part that interests me most is…",
    category: "trailing_copula",
    categoryLabel: "Unfinished observation",
    delivery: "Stop before naming the part.",
  },
];

export const recordingPrompts: RecordingPrompt[] = [
  ...completePrompts.map((prompt, index) => ({
    ...prompt,
    label: "complete" as const,
    order: index + 1,
  })),
  ...incompletePrompts.map((prompt, index) => ({
    ...prompt,
    label: "incomplete" as const,
    order: completePrompts.length + index + 1,
  })),
];
