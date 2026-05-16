export interface OrphanRule {
    /** Minimum words in element to apply (default: 4) */
    minWords?: number;
    /** Skip if computed font-size > this value (px or rem) */
    maxFontSize?: string;
    /** Skip if computed font-size < this value (px or rem) */
    minFontSize?: string;
    /** Words to keep together at end of text (default: 2) */
    minLastLineWords?: number;
    /** Max characters for the protected word group (default: 25) */
    maxProtectedChars?: number;
    /** Only apply to elements that span multiple lines */
    onlyMultiLine?: boolean;
}
export interface OrphanConfig {
    /** CSS selectors to target */
    selectors: string[];
    /** Rules controlling when to apply */
    rules?: OrphanRule;
    /** Re-apply on DOM mutations (default: false) */
    observe?: boolean;
    /** Re-apply on window resize (default: false) */
    responsive?: boolean;
    /** Show subtle dotted outline around fixed words (default: false) */
    demo?: boolean;
}
export type OrphanInput = string | OrphanConfig | OrphanConfig[];
export interface OrphanInstance {
    /** Re-process all matching elements */
    update(): void;
    /** Restore original text and disconnect observers */
    destroy(): void;
}
//# sourceMappingURL=types.d.ts.map