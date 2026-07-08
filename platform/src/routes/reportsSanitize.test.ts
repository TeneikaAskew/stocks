// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { renderReportHtml } from './ReportsPage';

describe('renderReportHtml', () => {
  it('strips script tags and inline handlers from report markdown', () => {
    const html = renderReportHtml('# Title\n\n<script>alert(1)</script>\n\n<img src=x onerror="alert(1)">');
    expect(html).not.toContain('<script');
    expect(html).not.toContain('onerror');
    expect(html).toContain('<h1');
  });
});
