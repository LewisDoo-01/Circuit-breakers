const pptxgen = require('pptxgenjs');
const pres = new pptxgen();

pres.layout = 'LAYOUT_16x9';
pres.author = 'VinUniversity';
pres.title = 'Model Context Protocol (MCP) - AICB P2T3 Day 26';

// ─── Colors ─────────────────────────────────────────────
const NAVY    = '3B5074';
const SECT    = '475B78';
const RED     = 'CC3333';
const WHT     = 'FFFFFF';
const TXT     = '333333';
const LT      = 'F2F2F2';
const MUT     = '999999';
const ICE     = 'CADCFC';
const CODE_BG = '2B2B2B';
const CALL_BG = 'F5F5F5';
const GRN     = '4CAF50';
const GRN_LT  = 'E8F5E9';
const BLU     = '2196F3';
const BLU_LT  = 'E3F2FD';
const ORG     = 'FF9800';
const ORG_LT  = 'FFF3E0';
const AMBER   = 'F39C12';
const TEAL    = '1B7A8A';
const DK_GRAY = '666666';

const W = 10, H = 5.625;
const SCRIPTS = '/Users/truongnh/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/8e04c055-393b-4520-bb5b-69cd365d72f7/73ab59a7-973d-496a-bf83-75990c16b58c/skills/pptx/scripts';

// ─── Helpers ────────────────────────────────────────────
function addFooter(s, n) {
  const y = H - 0.42;
  s.addText('Giảng viên (VinUni)', { x: 0.3, y, w: 3, h: 0.3, fontSize: 8, color: MUT, isTextBox: true, margin: 0 });
  s.addText('AICB · Ngày 26', { x: 3.5, y, w: 3, h: 0.3, fontSize: 8, color: MUT, align: 'center', isTextBox: true, margin: 0 });
  s.addText('Tuần 6    ' + n + ' / 26', { x: 7, y, w: 2.7, h: 0.3, fontSize: 8, color: MUT, align: 'right', isTextBox: true, margin: 0 });
}

function addHeader(s, title) {
  s.addShape('rect', { x: 0, y: 0, w: W, h: 0.6, fill: { color: NAVY } });
  s.addText(title, { x: 0.4, y: 0.07, w: 7.2, h: 0.46, fontSize: 17, bold: true, color: WHT, isTextBox: true, margin: 0 });
  s.addText('✔ VINUNIVERSITY', { x: 7.8, y: 0.12, w: 1.9, h: 0.36, fontSize: 9, color: WHT, align: 'right', isTextBox: true, margin: 0 });
}

function addSection(num, title, sub) {
  const s = pres.addSlide();
  s.background = { color: SECT };
  s.addText(num, { x: 5, y: 0.2, w: 4.5, h: 5.2, fontSize: 160, color: WHT, transparency: 82, align: 'right', valign: 'middle', bold: true, isTextBox: true, margin: 0 });
  s.addText(title, { x: 0.8, y: 1.2, w: 6.5, h: 2, fontSize: 38, color: WHT, bold: true, isTextBox: true, margin: 0 });
  s.addShape('line', { x: 0.8, y: 3.3, w: 1.5, h: 0, line: { color: RED, width: 3 } });
  if (sub) s.addText(sub, { x: 0.8, y: 3.5, w: 7, h: 0.8, fontSize: 14, color: ICE, isTextBox: true, margin: 0 });
}

function contentSlide(title, n) {
  const s = pres.addSlide();
  addHeader(s, title);
  addFooter(s, n);
  return s;
}

function addCallout(s, textArr, x, y, w, h) {
  s.addShape('rect', { x, y, w, h, fill: { color: CALL_BG }, line: { color: 'E0E0E0', width: 0.5 } });
  if (typeof textArr === 'string') {
    s.addText(textArr, { x: x + 0.15, y: y + 0.08, w: w - 0.3, h: h - 0.16, fontSize: 12, color: TXT, isTextBox: true, margin: 0, valign: 'middle' });
  } else {
    s.addText(textArr, { x: x + 0.15, y: y + 0.08, w: w - 0.3, h: h - 0.16, fontSize: 12, isTextBox: true, margin: 0, valign: 'middle' });
  }
}

function addNoteBox(s, textArr, x, y, w, h) {
  s.addShape('rect', { x, y, w, h, fill: { color: 'FFF8E1' }, line: { color: 'E0E0E0', width: 0.5 } });
  s.addShape('rect', { x, y, w: 0.06, h, fill: { color: AMBER } });
  if (typeof textArr === 'string') {
    s.addText(textArr, { x: x + 0.2, y: y + 0.08, w: w - 0.4, h: h - 0.16, fontSize: 11, color: TXT, isTextBox: true, margin: 0, valign: 'middle' });
  } else {
    s.addText(textArr, { x: x + 0.2, y: y + 0.08, w: w - 0.4, h: h - 0.16, fontSize: 11, isTextBox: true, margin: 0, valign: 'middle' });
  }
}

function diagBox(s, x, y, w, h, bgColor, text, opts) {
  s.addShape('roundRect', { x, y, w, h, fill: { color: bgColor }, rectRadius: 0.06 });
  s.addText(text, { x, y, w, h, fontSize: 9, color: WHT, align: 'center', valign: 'middle', isTextBox: true, margin: 0, ...(opts || {}) });
}

function diagBoxOutline(s, x, y, w, h, lineColor, text, opts) {
  s.addShape('roundRect', { x, y, w, h, fill: { color: WHT }, line: { color: lineColor, width: 1 }, rectRadius: 0.06 });
  s.addText(text, { x, y, w, h, fontSize: 9, color: TXT, align: 'center', valign: 'middle', isTextBox: true, margin: 0, ...(opts || {}) });
}

function arrow(s, x, y, w) {
  s.addText('→', { x, y, w, h: 0.3, fontSize: 14, color: MUT, align: 'center', valign: 'middle', isTextBox: true, margin: 0 });
}

// ════════════════════════════════════════════════════════
// SLIDE 1: Title
// ════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: SECT };
  s.addText('✔ VINUNIVERSITY', { x: 3, y: 0.3, w: 4, h: 0.6, fontSize: 18, color: WHT, align: 'center', bold: true, isTextBox: true, margin: 0 });
  s.addText('Model Context Protocol (MCP)', { x: 0.5, y: 1.4, w: 9, h: 1.2, fontSize: 40, color: WHT, bold: true, align: 'center', isTextBox: true, margin: 0 });
  s.addText('AICB-P2T3 · Ngày 26 · Chương 6 — Chuẩn hóa Tool Integration', { x: 1, y: 2.7, w: 8, h: 0.5, fontSize: 14, color: ICE, italic: true, align: 'center', isTextBox: true, margin: 0 });
  s.addText('Giảng viên', { x: 2, y: 3.6, w: 6, h: 0.5, fontSize: 20, color: 'FFD700', bold: true, align: 'center', isTextBox: true, margin: 0 });
  s.addText('VinUniversity · Phase 2 · Track 3 · Tuần 6', { x: 2, y: 4.2, w: 6, h: 0.4, fontSize: 12, color: ICE, align: 'center', isTextBox: true, margin: 0 });
}

// ════════════════════════════════════════════════════════
// SLIDE 2: Think About It
// ════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: SECT };
  s.addText('HÃY SUY NGHĨ...', { x: 0.5, y: 0.3, w: 3, h: 0.4, fontSize: 14, color: RED, bold: true, isTextBox: true, margin: 0 });
  s.addText('“MCP giải quyết vấn đề gì mà function calling thông thường không giải quyết được?”', {
    x: 1, y: 1.3, w: 7.5, h: 2.2, fontSize: 26, color: WHT, align: 'center', valign: 'middle', isTextBox: true, margin: 0
  });
  s.addText('Giữ câu hỏi này trong đầu khi học bài hôm nay', {
    x: 2, y: 4.2, w: 6, h: 0.4, fontSize: 12, color: MUT, align: 'center', isTextBox: true, margin: 0
  });
  s.addText('?', { x: 7.5, y: 1, w: 2, h: 3, fontSize: 120, color: WHT, transparency: 85, align: 'center', valign: 'middle', isTextBox: true, margin: 0 });
}

// ════════════════════════════════════════════════════════
// SLIDE 3: TOC (1/26)
// ════════════════════════════════════════════════════════
{
  const s = contentSlide('Nội dung bài học', 1);
  const items = [
    'Vấn đề N×M và tại sao cần MCP',
    'MCP Architecture',
    'Build MCP Server với Python SDK',
    'Security, Registry & Versioning',
    'Demo & Thực hành',
    'MCP trong thực tế 2026',
    'Real Use Cases & Useful Servers',
  ];
  items.forEach((item, i) => {
    s.addText((i + 1) + '.', { x: 0.5, y: 0.95 + i * 0.58, w: 0.45, h: 0.48, fontSize: 18, bold: true, color: TXT, isTextBox: true, margin: 0 });
    s.addText(item, { x: 1.05, y: 0.95 + i * 0.58, w: 7, h: 0.48, fontSize: 18, color: TXT, isTextBox: true, margin: 0 });
  });
}

// ════════════════════════════════════════════════════════
// SECTION 01: Van de N×M
// ════════════════════════════════════════════════════════
addSection('01', 'Vấn đề N×M và tại sao cần MCP', 'Mỗi provider một format riêng — integration nightmare');

// SLIDE 5: Function Calling — Van de N×M (2/26)
{
  const s = contentSlide('Function Calling — Vấn đề N×M', 2);

  // Left side: Before MCP
  s.addText('Trước MCP: N×M connections', { x: 0.4, y: 0.75, w: 4.2, h: 0.4, fontSize: 14, bold: true, color: TEAL, isTextBox: true, margin: 0 });
  // AI providers
  diagBoxOutline(s, 0.5, 1.3, 1.2, 0.35, BLU, 'OpenAI');
  diagBoxOutline(s, 0.5, 1.8, 1.2, 0.35, BLU, 'Anthropic');
  diagBoxOutline(s, 0.5, 2.3, 1.2, 0.35, BLU, 'Google');
  // Tools
  diagBoxOutline(s, 3.2, 1.3, 1.2, 0.35, GRN, 'Database');
  diagBoxOutline(s, 3.2, 1.8, 1.2, 0.35, GRN, 'GitHub');
  diagBoxOutline(s, 3.2, 2.3, 1.2, 0.35, GRN, 'Slack');
  // Connection lines (simplified)
  for (let i = 0; i < 3; i++) {
    for (let j = 0; j < 3; j++) {
      s.addShape('line', { x: 1.7, y: 1.48 + i * 0.5, w: 1.5, h: (j - i) * 0.5, line: { color: 'CCCCCC', width: 0.5 } });
    }
  }
  s.addText('3 × 3 = 9 adapters', { x: 0.5, y: 2.8, w: 4, h: 0.3, fontSize: 11, color: MUT, italic: true, isTextBox: true, margin: 0 });

  // Right side: After MCP
  s.addText('Sau MCP: N+M connections', { x: 5.3, y: 0.75, w: 4.2, h: 0.4, fontSize: 14, bold: true, color: TEAL, isTextBox: true, margin: 0 });
  diagBoxOutline(s, 5.4, 1.3, 1.1, 0.35, BLU, 'OpenAI');
  diagBoxOutline(s, 5.4, 1.8, 1.1, 0.35, BLU, 'Anthropic');
  diagBoxOutline(s, 5.4, 2.3, 1.1, 0.35, BLU, 'Google');
  diagBox(s, 7, 1.6, 0.9, 0.7, TEAL, 'MCP', { fontSize: 12, bold: true });
  diagBoxOutline(s, 8.3, 1.3, 1.1, 0.35, GRN, 'Database');
  diagBoxOutline(s, 8.3, 1.8, 1.1, 0.35, GRN, 'GitHub');
  diagBoxOutline(s, 8.3, 2.3, 1.1, 0.35, GRN, 'Slack');
  s.addText('3 + 3 = 6 adapters', { x: 5.4, y: 2.8, w: 4, h: 0.3, fontSize: 11, color: MUT, italic: true, isTextBox: true, margin: 0 });

  addCallout(s, [
    { text: 'MCP giống ', options: { color: TXT } },
    { text: 'USB-C', options: { bold: true, color: TXT } },
    { text: ' — một chuẩn kết nối cho mọi thiết bị, thay vì mỗi hãng một cổng riêng. Write once, run anywhere.', options: { color: TXT } },
  ], 0.4, 3.3, 9.2, 0.7);
}

// SLIDE 6: MCP Adoption (3/26)
{
  const s = contentSlide('MCP Adoption — Con số thực tế (2025–2026)', 3);

  // Stat cards
  const stats = [
    { val: '97M+', label: 'Monthly SDK\ndownloads' },
    { val: '10,000+', label: 'Community\nMCP servers' },
    { val: 'LF', label: 'Linux Foundation\ndonation' },
  ];
  stats.forEach((st, i) => {
    const x = 0.5 + i * 3.1;
    s.addShape('roundRect', { x, y: 1, w: 2.7, h: 1.8, fill: { color: LT }, rectRadius: 0.1 });
    s.addText(st.val, { x, y: 1.15, w: 2.7, h: 0.9, fontSize: 42, bold: true, color: RED, align: 'center', valign: 'middle', isTextBox: true, margin: 0 });
    s.addText(st.label, { x, y: 2.05, w: 2.7, h: 0.65, fontSize: 12, color: DK_GRAY, align: 'center', valign: 'top', isTextBox: true, margin: 0 });
  });

  addCallout(s, [
    { text: 'MCP không chỉ là Anthropic — đã được Google, Microsoft, OpenAI adopt. ', options: { color: TXT } },
    { text: 'A2A protocol', options: { bold: true, color: TXT } },
    { text: ' (Agent-to-Agent) complement MCP cho agent-to-agent communication.', options: { color: TXT } },
  ], 0.4, 3.4, 9.2, 0.7);
}

// SLIDE 7: Function Calling vs MCP (4/26)
{
  const s = contentSlide('Function Calling vs MCP', 4);

  // Left box: Function Calling
  s.addShape('roundRect', { x: 0.4, y: 0.85, w: 4.3, h: 3.2, fill: { color: LT }, rectRadius: 0.1 });
  s.addShape('rect', { x: 0.4, y: 0.85, w: 4.3, h: 0.5, fill: { color: NAVY } });
  s.addText('Function Calling (truyền thống)', { x: 0.5, y: 0.87, w: 4.1, h: 0.46, fontSize: 13, bold: true, color: WHT, isTextBox: true, margin: 0 });
  s.addText([
    { text: 'Tightly coupled to provider', options: { bullet: true, breakLine: true } },
    { text: 'OpenAI format ≠ Anthropic ≠ Google', options: { bullet: true, breakLine: true } },
    { text: 'Chỉ hỗ trợ tool calls', options: { bullet: true, breakLine: true, bold: true } },
    { text: 'Viết lại adapter mỗi khi đổi provider', options: { bullet: true } },
  ], { x: 0.7, y: 1.55, w: 3.8, h: 2.3, fontSize: 13, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 8 });

  // Right box: MCP
  s.addShape('roundRect', { x: 5.3, y: 0.85, w: 4.3, h: 3.2, fill: { color: LT }, rectRadius: 0.1 });
  s.addShape('rect', { x: 5.3, y: 0.85, w: 4.3, h: 0.5, fill: { color: TEAL } });
  s.addText('MCP (chuẩn mới)', { x: 5.4, y: 0.87, w: 4.1, h: 0.46, fontSize: 13, bold: true, color: WHT, isTextBox: true, margin: 0 });
  s.addText([
    { text: 'Universal, provider-agnostic', options: { bullet: true, breakLine: true } },
    { text: 'JSON-RPC 2.0 standard', options: { bullet: true, breakLine: true } },
    { text: 'Tools + Resources + Prompts + Sampling + Elicitation', options: { bullet: true, breakLine: true } },
    { text: 'Write tool once, any client dùng được', options: { bullet: true } },
  ], { x: 5.6, y: 1.55, w: 3.8, h: 2.3, fontSize: 13, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 8 });
}

// ════════════════════════════════════════════════════════
// SECTION 02: MCP Architecture
// ════════════════════════════════════════════════════════
addSection('02', 'MCP Architecture', 'Host → Client → Server → Tools');

// SLIDE 9: Architecture — Host, Client, Server (5/26)
{
  const s = contentSlide('MCP Architecture — Host, Client, Server', 5);

  // HOST box
  s.addShape('roundRect', { x: 0.3, y: 1.2, w: 1.6, h: 1.2, fill: { color: BLU_LT }, line: { color: BLU, width: 1 }, rectRadius: 0.08 });
  s.addText('HOST\nClaude Desktop / Cursor', { x: 0.3, y: 1.2, w: 1.6, h: 1.2, fontSize: 9, color: TXT, align: 'center', valign: 'middle', bold: true, isTextBox: true, margin: 0 });

  // Client 1 → Server 1
  diagBox(s, 2.3, 1.0, 1.0, 0.4, BLU, 'Client 1');
  s.addText('JSON-RPC', { x: 3.5, y: 1.0, w: 0.9, h: 0.4, fontSize: 8, color: MUT, align: 'center', valign: 'middle', isTextBox: true, margin: 0 });
  diagBox(s, 4.5, 1.0, 1.3, 0.4, ORG, 'Server 1\nPostgreSQL', { fontSize: 8 });
  // Tools
  diagBox(s, 6.2, 0.8, 1.0, 0.3, GRN, 'query_db', { fontSize: 8 });
  diagBox(s, 6.2, 1.2, 1.0, 0.3, GRN, 'insert_row', { fontSize: 8 });

  // Client 2 → Server 2
  diagBox(s, 2.3, 2.0, 1.0, 0.4, BLU, 'Client 2');
  s.addText('JSON-RPC', { x: 3.5, y: 2.0, w: 0.9, h: 0.4, fontSize: 8, color: MUT, align: 'center', valign: 'middle', isTextBox: true, margin: 0 });
  diagBox(s, 4.5, 2.0, 1.3, 0.4, ORG, 'Server 2\nGitHub', { fontSize: 8 });
  diagBox(s, 6.2, 1.8, 1.1, 0.3, GRN, 'create_issue', { fontSize: 8 });
  diagBox(s, 6.2, 2.2, 1.1, 0.3, GRN, 'list_repos', { fontSize: 8 });

  // Labels
  s.addText('1:1 connection', { x: 2.3, y: 0.65, w: 1.5, h: 0.3, fontSize: 8, color: MUT, italic: true, isTextBox: true, margin: 0 });

  // Bottom boxes
  s.addShape('roundRect', { x: 0.3, y: 3.2, w: 4.3, h: 1, fill: { color: CALL_BG }, rectRadius: 0.08 });
  s.addText([
    { text: 'Host ', options: { bold: true, color: RED } },
    { text: 'trusts', options: { bold: true, color: RED } },
    { text: ' Client (same process)\nClient ', options: { color: TXT } },
    { text: 'verifies', options: { bold: true, color: BLU } },
    { text: ' Server (auth)\nServer ', options: { color: TXT } },
    { text: 'validates', options: { bold: true, color: GRN } },
    { text: ' all inputs', options: { color: TXT } },
  ], { x: 0.5, y: 3.25, w: 3.9, h: 0.9, fontSize: 11, isTextBox: true, margin: 0 });

  s.addShape('roundRect', { x: 5.3, y: 3.2, w: 4.3, h: 1, fill: { color: CALL_BG }, rectRadius: 0.08 });
  s.addText([
    { text: 'stdio', options: { bold: true, color: TXT } },
    { text: ': same machine, low latency\n', options: { color: TXT } },
    { text: 'SSE/HTTP', options: { bold: true, color: TXT } },
    { text: ': remote, production\nCùng protocol, khác transport', options: { color: TXT } },
  ], { x: 5.5, y: 3.25, w: 3.9, h: 0.9, fontSize: 11, isTextBox: true, margin: 0 });
}

// SLIDE 10: MCP Primitives (6/26)
{
  const s = contentSlide('MCP Primitives — Không chỉ là Tool Calling', 6);

  const tblRows = [
    [
      { text: 'Primitive', options: { fill: { color: NAVY }, color: WHT, bold: true, fontSize: 12, align: 'left' } },
      { text: 'Vai trò', options: { fill: { color: NAVY }, color: WHT, bold: true, fontSize: 12, align: 'left' } },
      { text: 'Ai kiểm soát?', options: { fill: { color: NAVY }, color: WHT, bold: true, fontSize: 12, align: 'left' } },
      { text: 'Ví dụ', options: { fill: { color: NAVY }, color: WHT, bold: true, fontSize: 12, align: 'left' } },
    ],
    [
      { text: 'Tools', options: { bold: true, fontSize: 11 } },
      { text: 'Callable functions', options: { fontSize: 11 } },
      { text: 'LLM quyết định gọi', options: { fontSize: 11 } },
      { text: 'query_db(), send_email()', options: { fontSize: 10, fontFace: 'Courier New' } },
    ],
    [
      { text: 'Resources', options: { bold: true, fontSize: 11 } },
      { text: 'Read-only data (URI)', options: { fontSize: 11 } },
      { text: 'App cung cấp context', options: { fontSize: 11 } },
      { text: 'file://docs/guide.md', options: { fontSize: 10, fontFace: 'Courier New' } },
    ],
    [
      { text: 'Prompts', options: { bold: true, fontSize: 11 } },
      { text: 'Reusable templates', options: { fontSize: 11 } },
      { text: 'User chọn', options: { fontSize: 11 } },
      { text: 'summarize-code template', options: { fontSize: 10, fontFace: 'Courier New' } },
    ],
    [
      { text: 'Sampling', options: { bold: true, fontSize: 11 } },
      { text: 'LLM completions', options: { fontSize: 11 } },
      { text: 'Server yêu cầu', options: { fontSize: 11 } },
      { text: 'Server gọi LLM qua host', options: { fontSize: 10 } },
    ],
    [
      { text: 'Elicitation', options: { bold: true, fontSize: 11 } },
      { text: 'Structured input', options: { fontSize: 11 } },
      { text: 'Server hỏi user', options: { fontSize: 11 } },
      { text: 'Form input qua host UI', options: { fontSize: 10 } },
    ],
  ];
  s.addTable(tblRows, {
    x: 0.4, y: 0.8, w: 9.2,
    border: { type: 'solid', color: 'E0E0E0', pt: 0.5 },
    colW: [1.4, 2.2, 2.3, 3.3],
    rowH: [0.4, 0.4, 0.4, 0.4, 0.4, 0.4],
    margin: [3, 5, 3, 5],
  });

  addNoteBox(s, [
    { text: 'Lưu ý: ', options: { bold: true, color: AMBER } },
    { text: 'Hầu hết team chỉ dùng Tools — nhưng ', options: { color: TXT } },
    { text: 'Resources', options: { bold: true, color: TXT } },
    { text: ' và ', options: { color: TXT } },
    { text: 'Prompts', options: { bold: true, color: TXT } },
    { text: ' underutilized. Dùng Resources cho dynamic context injection thay vì hardcode vào system prompt.', options: { color: TXT } },
  ], 0.4, 3.75, 9.2, 0.65);
}

// SLIDE 11: Tool Discovery (7/26)
{
  const s = contentSlide('Tool Discovery — Agent tìm tool đúng lúc cần', 7);

  // Flow diagram
  const boxes = ['MCP Client', 'Initialize', 'tools/list', 'Tool Schemas', 'LLM chọn tool'];
  const colors = [BLU, MUT, GRN, ORG, RED];
  boxes.forEach((label, i) => {
    const x = 0.4 + i * 1.9;
    diagBox(s, x, 1.5, 1.5, 0.5, colors[i], label, { fontSize: 10, bold: true });
    if (i < boxes.length - 1) {
      s.addText('→', { x: x + 1.5, y: 1.5, w: 0.4, h: 0.5, fontSize: 16, color: MUT, align: 'center', valign: 'middle', isTextBox: true, margin: 0 });
    }
  });

  // Labels above arrows
  const labels = ['connect', 'request', 'response', 'inject'];
  labels.forEach((lbl, i) => {
    s.addText(lbl, { x: 0.4 + i * 1.9 + 1.3, y: 1.2, w: 0.9, h: 0.3, fontSize: 8, color: MUT, italic: true, align: 'center', isTextBox: true, margin: 0 });
  });

  // Feedback loop
  s.addText('tools/call → execute → return result', { x: 2, y: 2.3, w: 6, h: 0.3, fontSize: 10, color: MUT, italic: true, align: 'center', isTextBox: true, margin: 0 });

  addCallout(s, [
    { text: 'LLM chọn tool dựa trên ', options: { color: TXT } },
    { text: 'name + description', options: { bold: true, color: TXT } },
    { text: '. Mô tả rõ ràng, cụ thể = LLM chọn đúng tool. Mô tả mơ hồ = agent gọi sai tool → failure.', options: { color: TXT } },
  ], 0.4, 3.2, 9.2, 0.65);
}

// ════════════════════════════════════════════════════════
// SECTION 03: Build MCP Server with Python SDK
// ════════════════════════════════════════════════════════
addSection('03', 'Build MCP Server với Python SDK', 'FastMCP — decorator-based, production-ready');

// SLIDE 13: FastMCP (8/26)
{
  const s = contentSlide('FastMCP — Build server trong 20 dòng', 8);

  // Code block
  s.addShape('roundRect', { x: 0.4, y: 0.8, w: 4.8, h: 3.5, fill: { color: CODE_BG }, rectRadius: 0.08 });
  const code = `from mcp.server.fastmcp import FastMCP
mcp = FastMCP("sales-db")

@mcp.tool()
async def query_sales(
    region: str, quarter: str
) -> dict:
    """Query sales data by region
    and quarter. Returns revenue,
    units_sold, top_products."""
    result = await db.query(
        region=region, quarter=quarter
    )
    return result.to_dict()

@mcp.resource("sales://schema")
async def get_schema() -> str:
    return db.get_schema_ddl()`;
  s.addText(code, { x: 0.6, y: 0.9, w: 4.4, h: 3.3, fontSize: 9, fontFace: 'Courier New', color: 'E0E0E0', isTextBox: true, margin: 0 });

  // Right side
  s.addText('3 decorators:', { x: 5.5, y: 0.85, w: 4, h: 0.35, fontSize: 15, bold: true, color: TXT, isTextBox: true, margin: 0 });
  s.addText([
    { text: '1. @mcp.tool()', options: { bold: true, fontFace: 'Courier New', breakLine: true } },
    { text: ' — callable function\n', options: { breakLine: true } },
    { text: '2. @mcp.resource()', options: { bold: true, fontFace: 'Courier New', breakLine: true } },
    { text: ' — read-only data\n', options: { breakLine: true } },
    { text: '3. @mcp.prompt()', options: { bold: true, fontFace: 'Courier New' } },
    { text: ' — reusable template', options: {} },
  ], { x: 5.5, y: 1.3, w: 4.2, h: 1.6, fontSize: 12, color: TXT, isTextBox: true, margin: 0 });

  addNoteBox(s, [
    { text: 'Lưu ý: ', options: { bold: true, color: AMBER } },
    { text: 'Tool description (docstring) là ', options: { color: TXT } },
    { text: 'quan trọng nhất', options: { bold: true, color: TXT } },
    { text: '. LLM đọc description để quyết định gọi tool nào.', options: { color: TXT } },
  ], 5.5, 3.1, 4.2, 0.55);

  s.addText([
    { text: 'Error handling: ', options: { bold: true, color: TXT } },
    { text: 'Return structured errors, ', options: { color: TXT } },
    { text: 'không raise exceptions', options: { bold: true, color: RED } },
    { text: ' — client cần error message rõ ràng để retry/fallback.', options: { color: TXT } },
  ], { x: 5.5, y: 3.8, w: 4.2, h: 0.55, fontSize: 11, isTextBox: true, margin: 0 });
}

// SLIDE 14: Claude Desktop Integration (9/26)
{
  const s = contentSlide('Claude Desktop Integration', 9);

  // Config code block
  s.addShape('roundRect', { x: 0.4, y: 0.8, w: 4.6, h: 3.2, fill: { color: CODE_BG }, rectRadius: 0.08 });
  const config = `# claude_desktop_config.json
config = {
  "mcpServers": {
    "sales-db": {
      "command": "python",
      "args": ["-m", "sales_mcp"],
      "env": {
        "DB_URL": "postgresql://..."
      }
    },
    "github": {
      "command": "npx",
      "args": [
        "@modelcontextprotocol/
         server-github"
      ]
    }
  }
}`;
  s.addText(config, { x: 0.6, y: 0.9, w: 4.2, h: 3, fontSize: 9, fontFace: 'Courier New', color: 'E0E0E0', isTextBox: true, margin: 0 });

  // Right side
  s.addText('Workflow chuẩn:', { x: 5.3, y: 0.85, w: 4, h: 0.4, fontSize: 15, bold: true, color: TXT, isTextBox: true, margin: 0 });
  s.addText([
    { text: '1. Write', options: { bold: true } },
    { text: ' MCP server (Python/TS)', options: { breakLine: true } },
    { text: '2. Test', options: { bold: true } },
    { text: ' với MCP Inspector', options: { breakLine: true } },
    { text: '3. Config', options: { bold: true } },
    { text: '\n    claude_desktop_config.json', options: { breakLine: true } },
    { text: '4. E2E test', options: { bold: true } },
    { text: ' trong Claude Desktop', options: {} },
  ], { x: 5.5, y: 1.4, w: 4.2, h: 1.6, fontSize: 13, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 8 });

  addCallout(s, [
    { text: 'Web UI test tools ', options: { color: TXT } },
    { text: 'without LLM', options: { bold: true, color: TXT } },
    { text: ' — verify schemas, output format, error handling trước khi integrate.', options: { color: TXT } },
  ], 5.3, 3.15, 4.4, 0.45);

  s.addText([
    { text: 'Debugging: Inspector first → Claude Desktop logs → LangSmith traces', options: { color: MUT, italic: true } },
  ], { x: 5.3, y: 3.75, w: 4.4, h: 0.35, fontSize: 10, isTextBox: true, margin: 0 });
}

// ════════════════════════════════════════════════════════
// SECTION 04: Security, Registry & Versioning
// ════════════════════════════════════════════════════════
addSection('04', 'Security, Registry & Versioning', 'Production MCP cần auth, discovery, và backward compatibility');

// SLIDE 16: MCP Security — Defense in Depth (10/26)
{
  const s = contentSlide('MCP Security — Defense in Depth', 10);

  // Left: Security layers (stacked boxes)
  const layers = [
    { label: 'Transport Security: OAuth 2.0, TLS', color: 'E3F2FD' },
    { label: 'Input Validation: server-side', color: 'FFF3E0' },
    { label: 'Permission Scope: least privilege', color: GRN_LT },
    { label: 'Audit Log', color: 'FFEBEE' },
  ];
  layers.forEach((l, i) => {
    s.addShape('roundRect', { x: 0.5, y: 1.1 + i * 0.7, w: 3.5, h: 0.55, fill: { color: l.color }, line: { color: 'CCCCCC', width: 0.5 }, rectRadius: 0.06 });
    s.addText(l.label, { x: 0.7, y: 1.1 + i * 0.7, w: 3.1, h: 0.55, fontSize: 10, color: TXT, valign: 'middle', isTextBox: true, margin: 0 });
  });

  // Right: 4 layers explained
  s.addText('4 tầng bảo mật:', { x: 5.2, y: 0.85, w: 4, h: 0.35, fontSize: 15, bold: true, color: TXT, isTextBox: true, margin: 0 });
  s.addText([
    { text: '1. Transport', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': OAuth 2.0 cho SSE/HTTP, TLS encrypt\n', options: { breakLine: true } },
    { text: '2. Validation', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': validate tất cả inputs server-side\n', options: { breakLine: true } },
    { text: '3. Permissions', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': mỗi tool chỉ có quyền cần thiết\n', options: { breakLine: true } },
    { text: '4. Audit', options: { bold: true, bullet: true } },
    { text: ': log mọi tool call + kết quả', options: {} },
  ], { x: 5.4, y: 1.3, w: 4.3, h: 2, fontSize: 12, color: TXT, isTextBox: true, margin: 0 });

  addNoteBox(s, [
    { text: 'Lưu ý: ', options: { bold: true, color: AMBER } },
    { text: 'stdio transport (local) không cần OAuth — nhưng SSE/HTTP (production remote) ', options: { color: TXT } },
    { text: 'bắt buộc', options: { bold: true, color: RED } },
    { text: ' phải có auth. Đừng expose MCP server ra internet không có auth!', options: { color: TXT } },
  ], 0.4, 3.65, 9.2, 0.65);
}

// SLIDE 17: Tool Registry & Versioning (11/26)
{
  const s = contentSlide('Tool Registry & Versioning', 11);

  // Left: Diagram
  s.addShape('roundRect', { x: 0.5, y: 1.5, w: 1.0, h: 0.5, fill: { color: BLU_LT }, line: { color: BLU, width: 1 }, rectRadius: 0.06 });
  s.addText('Agent', { x: 0.5, y: 1.5, w: 1.0, h: 0.5, fontSize: 10, color: TXT, align: 'center', valign: 'middle', bold: true, isTextBox: true, margin: 0 });

  s.addShape('roundRect', { x: 2.0, y: 1.2, w: 1.6, h: 1.1, fill: { color: GRN_LT }, line: { color: GRN, width: 1 }, rectRadius: 0.08 });
  s.addText('Tool\nRegistry', { x: 2.0, y: 1.2, w: 1.6, h: 1.1, fontSize: 11, color: TXT, align: 'center', valign: 'middle', bold: true, isTextBox: true, margin: 0 });

  diagBox(s, 4.0, 1.15, 1.4, 0.4, BLU, 'DB Server v2.1', { fontSize: 9 });
  diagBox(s, 4.0, 1.75, 1.4, 0.4, GRN, 'GitHub v1.3', { fontSize: 9 });

  s.addText('query task', { x: 0.5, y: 1.15, w: 1.0, h: 0.3, fontSize: 8, color: MUT, italic: true, isTextBox: true, margin: 0 });
  s.addText('match', { x: 3.6, y: 1.05, w: 0.6, h: 0.3, fontSize: 8, color: MUT, italic: true, isTextBox: true, margin: 0 });

  // Right: Info box
  s.addShape('roundRect', { x: 5.5, y: 0.85, w: 4.2, h: 0.7, fill: { color: BLU_LT }, rectRadius: 0.08 });
  s.addText([
    { text: 'Tool Registry', options: { bold: true, color: BLU } },
    { text: ' — Central catalog — agent discovers tools at runtime matching task requirements', options: { color: TXT } },
  ], { x: 5.7, y: 0.9, w: 3.8, h: 0.6, fontSize: 12, isTextBox: true, margin: 0 });

  s.addText('Versioning rules:', { x: 5.5, y: 1.8, w: 4, h: 0.35, fontSize: 15, bold: true, color: TXT, isTextBox: true, margin: 0 });
  s.addText([
    { text: 'Semver', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': major.minor.patch\n', options: { breakLine: true } },
    { text: 'Breaking changes = ', options: { bullet: true, breakLine: true } },
    { text: 'major', options: { bold: true } },
    { text: ' bump\n', options: { breakLine: true } },
    { text: 'Deprecation: warn period trước khi remove old versions', options: { bullet: true, breakLine: true } },
    { text: '\n', options: { breakLine: true } },
    { text: 'Clients cần migration time', options: { bullet: true } },
  ], { x: 5.7, y: 2.2, w: 4, h: 1.8, fontSize: 12, color: TXT, isTextBox: true, margin: 0 });
}

// ════════════════════════════════════════════════════════
// SECTION 05: Demo & Thuc hanh
// ════════════════════════════════════════════════════════
addSection('05', 'Demo & Thực hành', 'Live demo + Lab: build MCP server từ scratch');

// SLIDE 19: Agent with MCP Database + GitHub Tools (12/26)
{
  const s = contentSlide('Agent với MCP Database + GitHub Tools', 12);
  s.addText([
    { text: '1. Setup', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': Claude Desktop + custom PostgreSQL MCP server + official GitHub MCP server\n', options: { breakLine: true } },
    { text: '2. Inspector test', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': verify tool schemas, output format, error handling\n', options: { breakLine: true } },
    { text: '3. Task', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': "Query sales DB rồi create GitHub issue with analysis" — requires cả 2 servers\n', options: { breakLine: true } },
    { text: '4. E2E', options: { bold: true, bullet: true } },
    { text: ': Claude routes query_db sang postgres-mcp, create_issue sang github-mcp seamlessly', options: {} },
  ], { x: 0.5, y: 0.85, w: 9, h: 2.8, fontSize: 14, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 10 });
}

// SLIDE 20: Demo Architecture (13/26)
{
  const s = contentSlide('Demo Architecture — Multi-Server MCP', 13);

  // User
  s.addShape('roundRect', { x: 0.3, y: 1.7, w: 0.9, h: 0.5, fill: { color: LT }, line: { color: MUT, width: 1 }, rectRadius: 0.06 });
  s.addText('User', { x: 0.3, y: 1.7, w: 0.9, h: 0.5, fontSize: 10, color: TXT, align: 'center', valign: 'middle', isTextBox: true, margin: 0 });
  s.addText('prompt', { x: 1.2, y: 1.7, w: 0.6, h: 0.3, fontSize: 8, color: MUT, italic: true, isTextBox: true, margin: 0 });

  // Claude Desktop
  s.addShape('roundRect', { x: 1.9, y: 1.3, w: 2.0, h: 1.3, fill: { color: BLU_LT }, line: { color: BLU, width: 1 }, rectRadius: 0.08 });
  s.addText('Claude Desktop\n(Host + LLM)', { x: 1.9, y: 1.3, w: 2.0, h: 1.3, fontSize: 11, color: TXT, align: 'center', valign: 'middle', bold: true, isTextBox: true, margin: 0 });

  // postgres-mcp
  s.addText('stdio', { x: 4.0, y: 1.15, w: 0.6, h: 0.3, fontSize: 8, color: MUT, italic: true, isTextBox: true, margin: 0 });
  diagBox(s, 4.7, 1.1, 1.5, 0.5, ORG, 'postgres-mcp', { fontSize: 10, bold: true });
  diagBox(s, 6.6, 0.9, 1.2, 0.35, GRN, 'query_sales', { fontSize: 9 });
  diagBox(s, 6.6, 1.35, 1.2, 0.35, GRN, 'get_schema', { fontSize: 9 });

  // github-mcp
  s.addText('stdio', { x: 4.0, y: 2.35, w: 0.6, h: 0.3, fontSize: 8, color: MUT, italic: true, isTextBox: true, margin: 0 });
  diagBox(s, 4.7, 2.3, 1.5, 0.5, ORG, 'github-mcp', { fontSize: 10, bold: true });
  diagBox(s, 6.6, 2.1, 1.2, 0.35, GRN, 'create_issue', { fontSize: 9 });
  diagBox(s, 6.6, 2.55, 1.2, 0.35, GRN, 'list_repos', { fontSize: 9 });

  addCallout(s, [
    { text: 'User hỏi: "phân tích doanh số Q3 rồi tạo issue" → Claude tự route ', options: { color: TXT } },
    { text: 'query_sales', options: { bold: true, fontFace: 'Courier New', color: TXT } },
    { text: ' sang postgres-mcp, nhận data, phân tích, rồi gọi ', options: { color: TXT } },
    { text: 'create_issue', options: { bold: true, fontFace: 'Courier New', color: TXT } },
    { text: ' sang github-mcp. ', options: { color: TXT } },
    { text: 'Seamless multi-tool orchestration.', options: { bold: true, color: TXT } },
  ], 0.3, 3.3, 9.4, 0.75);
}

// SLIDE 21: Lab #26 (14/26)
{
  const s = contentSlide('Lab #26', 14);

  s.addShape('roundRect', { x: 0.5, y: 1.5, w: 9, h: 2.2, fill: { color: CALL_BG }, rectRadius: 0.1 });
  s.addText([
    { text: 'Mục tiêu: ', options: { bold: true, color: RED } },
    { text: 'Build custom MCP server + test cross-client compatibility', options: { color: TXT, breakLine: true } },
    { text: '\n', options: { breakLine: true } },
    { text: 'Deliverable:    ', options: { bold: true, color: BLU } },
    { text: 'GitHub repo: MCP server (3 tools) + Inspector test screenshots + Claude Desktop integration demo', options: { color: TXT, breakLine: true } },
    { text: '\n', options: { breakLine: true } },
    { text: 'Thời gian: ', options: { bold: true, color: GRN } },
    { text: '2 giờ', options: { color: TXT } },
  ], { x: 0.8, y: 1.6, w: 8.4, h: 2, fontSize: 15, isTextBox: true, margin: 0 });
}

// SLIDE 22: Lab 26 — Steps (15/26)
{
  const s = contentSlide('Lab 26 — Các bước thực hành', 15);
  s.addText([
    { text: '1. Build MCP Server', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': FastMCP, expose 3 tools (search, insert, aggregate) cho database\n', options: { breakLine: true } },
    { text: '2. Add Resource', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': expose database schema qua @mcp.resource() cho dynamic context\n', options: { breakLine: true } },
    { text: '3. Test với Inspector', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': verify tool schemas, test calls, check error responses\n', options: { breakLine: true } },
    { text: '4. Claude Desktop', options: { bold: true, bullet: true } },
    { text: ': config json, E2E test, verify multi-tool routing', options: {} },
  ], { x: 0.5, y: 0.85, w: 9, h: 2.6, fontSize: 14, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 8 });

  addCallout(s, [
    { text: 'GitHub repo + README: tool descriptions, Inspector screenshots, Claude Desktop demo video (2 phút). ', options: { color: TXT } },
    { text: 'Bonus', options: { bold: true, color: TXT } },
    { text: ': implement auth cho SSE transport.', options: { color: TXT } },
  ], 0.4, 3.8, 9.2, 0.65);
}

// ════════════════════════════════════════════════════════
// SECTION 06: MCP trong thuc te 2026
// ════════════════════════════════════════════════════════
addSection('06', 'MCP trong thực tế 2026', 'Từ protocol mới sang ecosystem production-grade');

// SLIDE 24: MCP Ecosystem Snapshot (16/26)
{
  const s = contentSlide('MCP Ecosystem Snapshot (2025–2026)', 16);

  const stats = [
    { val: '10,000+', label: 'Active public\nMCP servers' },
    { val: '97M+', label: 'Monthly SDK\ndownloads' },
    { val: 'AAIF', label: 'Stewardship under\nLinux Foundation' },
  ];
  stats.forEach((st, i) => {
    const x = 0.5 + i * 3.1;
    s.addShape('roundRect', { x, y: 0.9, w: 2.7, h: 1.7, fill: { color: LT }, rectRadius: 0.1 });
    s.addText(st.val, { x, y: 1.05, w: 2.7, h: 0.8, fontSize: 40, bold: true, color: RED, align: 'center', valign: 'middle', isTextBox: true, margin: 0 });
    s.addText(st.label, { x, y: 1.85, w: 2.7, h: 0.6, fontSize: 12, color: DK_GRAY, align: 'center', valign: 'top', isTextBox: true, margin: 0 });
  });

  addCallout(s, [
    { text: 'MCP đã đi từ "Anthropic protocol" sang ', options: { color: TXT } },
    { text: 'vendor-neutral standard', options: { bold: true, color: TXT } },
    { text: ': ChatGPT, Cursor, Gemini, Microsoft Copilot, VS Code đều đã xuất hiện trong ecosystem adopt/support.', options: { color: TXT } },
  ], 0.4, 3.2, 9.2, 0.7);
}

// SLIDE 25: MCP 2026 — Differences (17/26)
{
  const s = contentSlide('MCP 2026 — Có gì khác giai đoạn đầu?', 17);
  s.addText([
    { text: 'Transport guidance rõ hơn', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': remote production đang nghiêng về streamable-http; SSE dần trở thành legacy/deprecated path ở nhiều client\n', options: { breakLine: true } },
    { text: 'Capability negotiation', options: { bold: true, bullet: true, breakLine: true } },
    { text: ' trở thành tư duy cốt lõi: client và server khai báo rõ hỗ trợ gì trước khi dùng\n', options: { breakLine: true } },
    { text: 'Không chỉ tools', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': resources, prompts, roots, sampling, elicitation đều đã có vai trò thực tế hơn\n', options: { breakLine: true } },
    { text: 'Scale problem xuất hiện thật', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': khi một host có hàng trăm tools, context window và latency trở thành bottleneck\n', options: { breakLine: true } },
    { text: 'Governance trưởng thành', options: { bold: true, bullet: true } },
    { text: ': MCP được đưa vào Agentic AI Foundation để tránh lock-in theo một vendor', options: {} },
  ], { x: 0.5, y: 0.8, w: 9, h: 3, fontSize: 12, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 4 });

  addNoteBox(s, [
    { text: 'Lưu ý: ', options: { bold: true, color: AMBER } },
    { text: 'Nếu deck/team của bạn vẫn nghĩ MCP chỉ là "function calling nhưng tên mới", thì đang bỏ lỡ phần quan trọng nhất: ', options: { color: TXT } },
    { text: 'tool discovery, context control, và multi-client interoperability', options: { bold: true, color: TXT } },
    { text: '.', options: { color: TXT } },
  ], 0.4, 3.95, 9.2, 0.7);
}

// SLIDE 26: 6 Primitives (18/26)
{
  const s = contentSlide('6 Primitives Quan Trọng Của MCP', 18);

  // Left column
  s.addText([
    { text: '1. Tools', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': model thực hiện action hoặc query\n', options: { breakLine: true } },
    { text: '2. Resources', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': host đọc data/context theo URI\n', options: { breakLine: true } },
    { text: '3. Prompts', options: { bold: true, bullet: true } },
    { text: ': reusable interaction templates', options: {} },
  ], { x: 0.5, y: 0.8, w: 4.3, h: 2.2, fontSize: 13, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 8 });

  // Right column
  s.addText([
    { text: '4. Roots', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': client chia sẻ workspace roots an toàn cho server\n', options: { breakLine: true } },
    { text: '5. Sampling', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': server yêu cầu host/LLM suy luận thêm\n', options: { breakLine: true } },
    { text: '6. Elicitation', options: { bold: true, bullet: true } },
    { text: ': server xin thêm thông tin từ user qua host', options: {} },
  ], { x: 5.2, y: 0.8, w: 4.5, h: 2.2, fontSize: 13, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 8 });

  // Bottom boxes
  s.addShape('roundRect', { x: 0.5, y: 3.2, w: 4.3, h: 0.8, fill: { color: BLU_LT }, rectRadius: 0.08 });
  s.addText([
    { text: 'Ba primitive này trả lời câu hỏi: server\n', options: { color: TXT } },
    { text: 'có thể cung cấp gì', options: { bold: true, color: TXT } },
    { text: ' cho host?', options: { color: TXT } },
  ], { x: 0.7, y: 3.25, w: 3.9, h: 0.7, fontSize: 11, isTextBox: true, margin: 0, valign: 'middle' });

  s.addShape('roundRect', { x: 5.2, y: 3.2, w: 4.5, h: 0.8, fill: { color: ORG_LT }, rectRadius: 0.08 });
  s.addText([
    { text: 'Ba primitive này trả lời câu hỏi: server\n', options: { color: TXT } },
    { text: 'cần host hỗ trợ gì', options: { bold: true, color: TXT } },
    { text: ' để hoàn tất workflow?', options: { color: TXT } },
  ], { x: 5.4, y: 3.25, w: 4.1, h: 0.7, fontSize: 11, isTextBox: true, margin: 0, valign: 'middle' });

  s.addText([
    { text: 'Design takeaway: MCP là protocol cho ', options: { color: MUT, italic: true } },
    { text: 'context exchange', options: { bold: true, italic: true, color: MUT } },
    { text: ', không chỉ protocol cho "tool call".', options: { color: MUT, italic: true } },
  ], { x: 0.5, y: 4.2, w: 9, h: 0.35, fontSize: 11, isTextBox: true, margin: 0 });
}

// ════════════════════════════════════════════════════════
// SECTION 07: Real Use Cases & Useful Servers
// ════════════════════════════════════════════════════════
addSection('07', 'Real Use Cases & Useful Servers', 'MCP có giá trị nhất khi ghép context, action và policy lại với nhau');

// SLIDE 28: Real MCP Servers (19/26)
{
  const s = contentSlide('Real MCP Servers Đang Được Dùng Nhiều', 19);

  const tblRows = [
    [
      { text: 'Server', options: { fill: { color: NAVY }, color: WHT, bold: true, fontSize: 11, align: 'left' } },
      { text: 'Loại', options: { fill: { color: NAVY }, color: WHT, bold: true, fontSize: 11, align: 'left' } },
      { text: 'Dùng để làm gì', options: { fill: { color: NAVY }, color: WHT, bold: true, fontSize: 11, align: 'left' } },
      { text: 'Khi nào nên dùng', options: { fill: { color: NAVY }, color: WHT, bold: true, fontSize: 11, align: 'left' } },
    ],
    [
      { text: 'GitHub MCP', options: { bold: true, fontSize: 10 } },
      { text: 'official', options: { fontSize: 10 } },
      { text: 'repo, issue, PR, code search', options: { fontSize: 10 } },
      { text: 'Agent code theo ticket-to-PR loop', options: { fontSize: 10 } },
    ],
    [
      { text: 'Sentry MCP', options: { bold: true, fontSize: 10 } },
      { text: 'official', options: { fontSize: 10 } },
      { text: 'errors, stack trace, release regression', options: { fontSize: 10 } },
      { text: 'Debug production issue rồi mở fix/issue ngay', options: { fontSize: 10 } },
    ],
    [
      { text: 'OpenAI Docs MCP', options: { bold: true, fontSize: 10 } },
      { text: 'official', options: { fontSize: 10 } },
      { text: 'docs search + page fetch', options: { fontSize: 10 } },
      { text: 'Codex/Cursor cần đúng API/schema mới nhất', options: { fontSize: 10 } },
    ],
    [
      { text: 'Context7 MCP', options: { bold: true, fontSize: 10 } },
      { text: 'de-facto standard', options: { fontSize: 10 } },
      { text: 'version-specific library docs', options: { fontSize: 10 } },
      { text: 'Code với framework/library thay đổi nhanh', options: { fontSize: 10 } },
    ],
    [
      { text: 'Playwright MCP', options: { bold: true, fontSize: 10 } },
      { text: 'official', options: { fontSize: 10 } },
      { text: 'browser automation, repro UI, E2E checks', options: { fontSize: 10 } },
      { text: 'Tái hiện bug UI và verify fix end-to-end', options: { fontSize: 10 } },
    ],
    [
      { text: 'Slack / Notion MCP', options: { bold: true, fontSize: 10 } },
      { text: 'official SaaS', options: { fontSize: 10 } },
      { text: 'team chat + specs + wiki content', options: { fontSize: 10 } },
      { text: 'Lấy quyết định, requirement, handoff context', options: { fontSize: 10 } },
    ],
  ];
  s.addTable(tblRows, {
    x: 0.3, y: 0.75, w: 9.4,
    border: { type: 'solid', color: 'E0E0E0', pt: 0.5 },
    colW: [1.7, 1.3, 3.2, 3.2],
    rowH: [0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35],
    margin: [2, 4, 2, 4],
  });

  addCallout(s, [
    { text: 'Chọn MCP theo ', options: { color: TXT } },
    { text: 'workflow thật', options: { bold: true, color: TXT } },
    { text: ': code → GitHub, prod incident → Sentry, docs/API → OpenAI Docs hoặc Context7, UI bug → Playwright. Tránh cài "tool zoo" không gắn với task.', options: { color: TXT } },
  ], 0.3, 3.7, 9.4, 0.6);
}

// SLIDE 29: Local STDIO vs Remote HTTP MCP (20/26)
{
  const s = contentSlide('Local STDIO vs Remote HTTP MCP', 20);

  // Left box
  s.addShape('roundRect', { x: 0.4, y: 0.85, w: 4.3, h: 3.3, fill: { color: LT }, rectRadius: 0.1 });
  s.addShape('rect', { x: 0.4, y: 0.85, w: 4.3, h: 0.5, fill: { color: NAVY } });
  s.addText('STDIO (local-first)', { x: 0.5, y: 0.87, w: 4.1, h: 0.46, fontSize: 13, bold: true, color: WHT, isTextBox: true, margin: 0 });
  s.addText([
    { text: 'Chạy process local, setup nhanh', options: { bullet: true, breakLine: true } },
    { text: 'Phù hợp filesystem, git, scripts nội bộ', options: { bullet: true, breakLine: true } },
    { text: 'Dễ dev/test với Inspector', options: { bullet: true, breakLine: true } },
    { text: 'Trust boundary nhỏ hơn, ít phụ thuộc network', options: { bullet: true } },
  ], { x: 0.7, y: 1.6, w: 3.8, h: 2.3, fontSize: 13, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 10 });

  // Right box
  s.addShape('roundRect', { x: 5.3, y: 0.85, w: 4.3, h: 3.3, fill: { color: LT }, rectRadius: 0.1 });
  s.addShape('rect', { x: 5.3, y: 0.85, w: 4.3, h: 0.5, fill: { color: TEAL } });
  s.addText('HTTP / Streamable HTTP (shared service)', { x: 5.4, y: 0.87, w: 4.1, h: 0.46, fontSize: 12, bold: true, color: WHT, isTextBox: true, margin: 0 });
  s.addText([
    { text: 'Phù hợp SaaS hoặc shared org service', options: { bullet: true, breakLine: true } },
    { text: 'Hỗ trợ auth, OAuth, centralized rollout', options: { bullet: true, breakLine: true } },
    { text: 'Nhiều clients dùng chung một endpoint', options: { bullet: true, breakLine: true } },
    { text: 'Production remote nên ưu tiên SSE legacy hơn', options: { bullet: true } },
  ], { x: 5.6, y: 1.6, w: 3.8, h: 2.3, fontSize: 13, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 10 });
}

// ════════════════════════════════════════════════════════
// SECTION 08: Best Practices
// ════════════════════════════════════════════════════════
addSection('08', 'Best Practices với Codex & Claude Code', 'Dùng MCP như infrastructure, không dùng như "tool zoo"');

// SLIDE 31: Claude Code + MCP Best Practices (21/26)
{
  const s = contentSlide('Claude Code + MCP — Best Practices Thực Dụng', 21);
  s.addText([
    { text: 'Chọn đúng scope', options: { bold: true, bullet: true } },
    { text: ': local cho thử nhanh, project khi muốn share qua .mcp.json, user cho default cá nhân nhiều repo', options: { breakLine: true } },
    { text: 'Ưu tiên remote HTTP', options: { bold: true, bullet: true } },
    { text: ': dễ OAuth, rollout và policy hơn; chỉ giữ SSE nếu server cũ chưa support transport mới', options: { breakLine: true } },
    { text: 'Tận dụng Tool Search', options: { bold: true, bullet: true } },
    { text: ': Claude chỉ nạp tool khi cần, nên server instructions phải nói rõ "khi nào cần search server này"', options: { breakLine: true } },
    { text: 'Giữ instructions ngắn và front-load ý chính', options: { bold: true, bullet: true } },
    { text: ': đừng nhét prose dài; phần quan trọng phải xuất hiện sớm', options: { breakLine: true } },
    { text: 'Dùng hooks cho guardrail', options: { bold: true, bullet: true } },
    { text: ': match mcp__server__tool để log write, block path nguy hiểm, auto-run test sau edit', options: { breakLine: true } },
    { text: 'Giảm output size', options: { bold: true, bullet: true } },
    { text: ': trả summary + ID/URI để fetch tiếp, đừng dump JSON lớn làm chậm agent và đốt context', options: {} },
  ], { x: 0.5, y: 0.8, w: 9, h: 4, fontSize: 12, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 6 });
}

// SLIDE 32: Codex + MCP Best Practices (22/26)
{
  const s = contentSlide('Codex + MCP — Best Practices Thực Dụng', 22);
  s.addText([
    { text: 'Dùng AGENTS.md để ép thói quen tốt', options: { bold: true, bullet: true } },
    { text: ': ví dụ "luôn consult OpenAI Docs MCP khi câu hỏi liên quan OpenAI API/Codex"', options: { breakLine: true } },
    { text: 'Server label ngắn, mô tả đúng', options: { bold: true, bullet: true } },
    { text: ': tên rõ nghĩa giúp agent chọn đúng server khi có nhiều MCP cùng lúc', options: { breakLine: true } },
    { text: 'Thiết kế read path trước write path', options: { bold: true, bullet: true } },
    { text: ': docs/search/fetch trước, mutation sau; review/debug thường không cần write ngay', options: { breakLine: true } },
    { text: 'Nếu build remote MCP', options: { bold: true, bullet: true } },
    { text: ': bắt đầu bằng cặp search + fetch để agent tìm rồi đọc sâu đúng chỗ', options: { breakLine: true } },
    { text: 'Mô tả tool theo kiểu hành động', options: { bold: true, bullet: true } },
    { text: ': thêm "Use this when...", edge cases, enum, input shape để giảm gọi nhầm tool', options: { breakLine: true } },
    { text: 'Khóa phạm vi bằng approval/allowlist', options: { bold: true, bullet: true } },
    { text: ': chỉ mở những tool cần cho task; write actions nhạy cảm nên giữ human approval', options: {} },
  ], { x: 0.5, y: 0.8, w: 9, h: 3.6, fontSize: 12, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 4 });

  s.addText([
    { text: 'Mental model: Codex nên ', options: { color: MUT, italic: true } },
    { text: 'biết', options: { bold: true, italic: true, color: MUT } },
    { text: ' đúng context ', options: { color: MUT, italic: true } },
    { text: 'trước', options: { bold: true, italic: true, color: MUT } },
    { text: ', rồi mới ', options: { color: MUT, italic: true } },
    { text: 'hành động', options: { bold: true, italic: true, color: MUT } },
    { text: ' sau.', options: { color: MUT, italic: true } },
  ], { x: 0.5, y: 4.5, w: 9, h: 0.35, fontSize: 11, isTextBox: true, margin: 0 });
}

// SLIDE 33: 3 Workflow Patterns (23/26)
{
  const s = contentSlide('3 Workflow Patterns Có ROI Cao', 23);
  s.addText([
    { text: '1. Ticket → code → PR', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': GitHub MCP + docs MCP. Agent đọc issue/spec, sửa code, mở PR với context đúng.\n', options: { breakLine: true } },
    { text: '2. Prod error → root cause', options: { bold: true, bullet: true, breakLine: true } },
    { text: ': Sentry MCP + GitHub MCP. Agent lấy stack trace, map sang commit/release, rồi draft fix hoặc issue.\n', options: { breakLine: true } },
    { text: '3. Library upgrade → code migration', options: { bold: true, bullet: true } },
    { text: ': Context7/OpenAI Docs MCP + Playwright MCP. Agent đọc doc version mới, refactor, rồi verify UI flow.', options: {} },
  ], { x: 0.5, y: 0.85, w: 9, h: 2.5, fontSize: 13, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 8 });

  addNoteBox(s, [
    { text: 'Lưu ý: ', options: { bold: true, color: AMBER } },
    { text: 'Pattern tốt nhất là pattern có ', options: { color: TXT } },
    { text: 'closed loop', options: { bold: true, color: TXT } },
    { text: ': đọc đúng context → hành động nhỏ → verify ngay. MCP mạnh nhất khi có feedback loop, không chỉ khi có nhiều tools.', options: { color: TXT } },
  ], 0.4, 3.65, 9.2, 0.7);
}

// SLIDE 34: Security & Governance Anti-Patterns (24/26)
{
  const s = contentSlide('Security & Governance Anti-Patterns', 24);
  s.addText([
    { text: '1. Expose remote MCP không auth', options: { bold: true, bullet: true } },
    { text: ': chấp nhận cho internet gọi tool nội bộ', options: { breakLine: true } },
    { text: '2. Tin "read-only" tuyệt đối', options: { bold: true, bullet: true } },
    { text: ': prompt injection vẫn có thể biến read path thành data exfiltration path', options: { breakLine: true } },
    { text: '3. Nhồi quá nhiều tools vào context', options: { bold: true, bullet: true } },
    { text: ': model tốn token để đọc catalog thay vì giải task', options: { breakLine: true } },
    { text: '4. Tool descriptions mơ hồ', options: { bold: true, bullet: true } },
    { text: ': model gọi sai tool dù backend đúng', options: { breakLine: true } },
    { text: '5. Không log/audit', options: { bold: true, bullet: true } },
    { text: ': đến lúc có incident thì không biết tool nào đã được gọi', options: { breakLine: true } },
    { text: '6. Mix sandbox và production credentials', options: { bold: true, bullet: true } },
    { text: ': local experiment nhưng luôn dùng token prod full quyền', options: {} },
  ], { x: 0.5, y: 0.8, w: 9, h: 3, fontSize: 12, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 4 });

  addNoteBox(s, [
    { text: 'Lưu ý: ', options: { bold: true, color: AMBER } },
    { text: 'Trusting MCP developer là ', options: { color: TXT } },
    { text: 'cần', options: { bold: true, color: TXT } },
    { text: ', nhưng vẫn ', options: { color: TXT } },
    { text: 'không đủ', options: { bold: true, color: RED } },
    { text: '. Cần thêm permissioning, output review, write confirmation, và audit.', options: { color: TXT } },
  ], 0.4, 3.95, 9.2, 0.6);
}

// SLIDE 35: Production Checklist (25/26)
{
  const s = contentSlide('Production Checklist Cho MCP', 25);
  const items = [
    'Bắt đầu bằng workflow thật: ticket → code, dashboard → issue, docs → patch',
    'Thiết kế tool names + descriptions để model chọn đúng ngay từ đầu',
    'Trả output gọn; để raw payload lớn trong resource hoặc fetch-on-demand',
    'Dùng Inspector trước khi test trong client thật',
    'Chọn transport đúng: stdio cho local access, HTTP cho shared service',
    'Tách read/write scopes, log mọi write action, thêm human confirmation khi cần',
    'Với Claude Code/Codex: hướng dẫn agent bằng server naming, instructions, AGENTS.md, hooks/policies',
  ];
  items.forEach((item, i) => {
    s.addText('☑', { x: 0.4, y: 0.85 + i * 0.55, w: 0.35, h: 0.45, fontSize: 16, color: GRN, isTextBox: true, margin: 0 });
    s.addText(item, { x: 0.8, y: 0.85 + i * 0.55, w: 8.8, h: 0.45, fontSize: 12, color: TXT, isTextBox: true, margin: 0, valign: 'middle' });
  });
}

// SLIDE 36: Key Takeaways (25/26)
{
  const s = contentSlide('Tổng kết — Key Takeaways', 25);

  s.addShape('roundRect', { x: 0.4, y: 0.75, w: 9.2, h: 0.45, fill: { color: CALL_BG }, rectRadius: 0.06 });
  s.addText([
    { text: 'Những ý chính cần nhớ', options: { bold: true, color: TXT } },
    { text: ' trước khi sang bài tiếp theo', options: { color: TXT } },
  ], { x: 0.6, y: 0.78, w: 8.8, h: 0.4, fontSize: 14, isTextBox: true, margin: 0 });

  const takeaways = [
    ['1', 'MCP chuẩn hóa tool integration — build quality MCP servers, ', 'không', ' build custom adapters per provider'],
    ['2', 'MCP Inspector là developer essential — test locally ', 'trước khi', ' LLM integration, tiết kiệm hàng giờ debug'],
    ['3', 'Resources & Prompts underutilized — dùng cho dynamic context injection, không chỉ mỗi Tools', '', ''],
    ['4', 'Tool description quyết định thành bại — LLM chọn tool 100% dựa trên name + description', '', ''],
  ];
  takeaways.forEach((t, i) => {
    const y = 1.4 + i * 0.8;
    // Number circle
    s.addShape('roundRect', { x: 0.5, y: y + 0.05, w: 0.45, h: 0.45, fill: { color: NAVY }, rectRadius: 0.22 });
    s.addText(t[0], { x: 0.5, y: y + 0.05, w: 0.45, h: 0.45, fontSize: 14, color: WHT, bold: true, align: 'center', valign: 'middle', isTextBox: true, margin: 0 });
    // Description
    if (t[2]) {
      s.addText([
        { text: t[1], options: { color: TXT } },
        { text: t[2], options: { bold: true, color: TXT } },
        { text: t[3], options: { color: TXT } },
      ], { x: 1.15, y: y, w: 8.3, h: 0.6, fontSize: 12, isTextBox: true, margin: 0, valign: 'middle' });
    } else {
      s.addText(t[1], { x: 1.15, y, w: 8.3, h: 0.6, fontSize: 12, color: TXT, isTextBox: true, margin: 0, valign: 'middle' });
    }
    // Separator line
    if (i < 3) {
      s.addShape('line', { x: 0.5, y: y + 0.7, w: 9.1, h: 0, line: { color: 'E0E0E0', width: 0.5 } });
    }
  });
}

// SLIDE 37: Next Steps (26/26)
{
  const s = contentSlide('Tiếp theo & Bài tập', 26);

  // Left box: Next lesson
  s.addShape('roundRect', { x: 0.4, y: 1, w: 4.5, h: 2.5, fill: { color: CALL_BG }, rectRadius: 0.1 });
  s.addText('Ngày 27: Human-in-the-Loop UX', { x: 0.6, y: 1.1, w: 4.1, h: 0.45, fontSize: 15, bold: true, color: TXT, isTextBox: true, margin: 0 });
  s.addText('"Tools connected — tiếp theo thiết kế tương tác người-agent: khi nào agent tự quyết, khi nào cần xin phép?"', {
    x: 0.6, y: 1.7, w: 4.1, h: 1.5, fontSize: 13, color: DK_GRAY, italic: true, isTextBox: true, margin: 0
  });

  // Right box: Homework
  s.addShape('roundRect', { x: 5.2, y: 1, w: 4.5, h: 2.5, fill: { color: CALL_BG }, rectRadius: 0.1 });
  s.addText([
    { text: 'Hoàn thành Lab 26: MCP server + Inspector test', options: { bullet: true, breakLine: true } },
    { text: 'Đọc: MCP Specification\n(modelcontextprotocol.io/spec)', options: { bullet: true } },
  ], { x: 5.4, y: 1.3, w: 4.1, h: 2, fontSize: 14, color: TXT, isTextBox: true, margin: 0, paraSpaceAfter: 14 });
}

// ════════════════════════════════════════════════════════
// SLIDE 38: Q&A
// ════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: SECT };
  s.addText('Hỏi & Đáp', { x: 1, y: 1.5, w: 8, h: 1.5, fontSize: 56, color: WHT, bold: true, align: 'center', valign: 'middle', isTextBox: true, margin: 0 });
  s.addShape('line', { x: 3.5, y: 3.2, w: 3, h: 0, line: { color: RED, width: 3 } });
  s.addText('MCP có thay thế hoàn toàn function calling không? Hay dùng song song?', {
    x: 1.5, y: 3.5, w: 7, h: 0.8, fontSize: 14, color: ICE, italic: true, align: 'center', isTextBox: true, margin: 0
  });
}

// ════════════════════════════════════════════════════════
// SLIDE 39: Thank You
// ════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: SECT };
  s.addText('✔ VINUNIVERSITY', { x: 3, y: 0.5, w: 4, h: 0.8, fontSize: 20, color: WHT, align: 'center', bold: true, isTextBox: true, margin: 0 });
  s.addText('Cảm ơn!', { x: 1, y: 1.8, w: 8, h: 1.2, fontSize: 52, color: WHT, bold: true, align: 'center', isTextBox: true, margin: 0 });
  s.addShape('line', { x: 3.5, y: 3.1, w: 3, h: 0, line: { color: RED, width: 3 } });
  s.addText('AICB-P2T3 · Ngày 26 · Model Context Protocol (MCP)', { x: 1, y: 3.4, w: 8, h: 0.4, fontSize: 13, color: ICE, align: 'center', isTextBox: true, margin: 0 });
  s.addText('github.com/vinuni-aicb', { x: 1, y: 3.9, w: 8, h: 0.35, fontSize: 12, color: WHT, align: 'center', isTextBox: true, margin: 0 });
  s.addText([
    { text: 'Liên hệ: ', options: { color: ICE } },
    { text: 'instructor@vinuni.edu.vn', options: { color: RED } },
  ], { x: 1, y: 4.3, w: 8, h: 0.35, fontSize: 12, align: 'center', isTextBox: true, margin: 0 });
}

// ════════════════════════════════════════════════════════
// SAVE
// ════════════════════════════════════════════════════════
const outPath = '/Users/truongnh/work/day25-circuit-breakers/MCP_Day26_VinUni.pptx';
pres.writeFile({ fileName: outPath }).then(() => {
  console.log('Created: ' + outPath);
}).catch(err => {
  console.error('Error:', err);
});
