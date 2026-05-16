import type { OrphanRule } from './types';
export declare function resolveRule(rule?: OrphanRule): Required<OrphanRule>;
export declare function parsePx(value: string): number | null;
export declare function isMultiLine(el: HTMLElement): boolean;
export declare function shouldApply(el: HTMLElement, words: string[], rule: Required<OrphanRule>): boolean;
//# sourceMappingURL=rules.d.ts.map