/**
 * Text direction, decided per message rather than per page (project rule:
 * "detect the message language, not the page language"). A conversation can mix
 * an Arabic question with a French source excerpt, so each bubble is laid out on
 * its own.
 */

/** Arabic block + supplement + extended-A + presentation forms. */
const RTL_SCRIPT = /[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/;

export type Direction = "rtl" | "ltr";

/**
 * Direction for one piece of text. The backend's detected `language` wins when
 * we have it (the pipeline runs lingua-py on the full text); while an answer is
 * still streaming we only have the partial text, so we sniff the script.
 */
export function directionOf(text: string, language?: string | null): Direction {
  if (language) return language === "ar" ? "rtl" : "ltr";
  return RTL_SCRIPT.test(text) ? "rtl" : "ltr";
}
