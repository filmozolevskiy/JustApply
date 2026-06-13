#!/usr/bin/env python3
import os
import sys
import json
import html
import re
import argparse
import webbrowser
from datetime import datetime

# Simple, zero-dependency Markdown-to-HTML parser
def md_to_html(md_text):
    if not md_text:
        return ""
    
    # Escape HTML entities first, except we will preserve our own tags later
    text = html.escape(md_text)
    
    # Pre-formatted code blocks
    code_blocks = []
    def save_code_block(match):
        lang = match.group(1) or "python"
        code = match.group(2)
        # Decode HTML escape characters inside code blocks to allow Prism to handle it
        code_decoded = html.unescape(code)
        code_blocks.append((lang, code_decoded))
        return f"<!--CODE_BLOCK_{len(code_blocks)-1}-->"
    
    # Match ```lang ... ``` blocks
    text = re.sub(r'```(\w*)\n(.*?)\n```', save_code_block, text, flags=re.DOTALL)
    
    # Inline code: `code`
    text = re.sub(r'`([^`]+)`', r'<code class="px-1.5 py-0.5 rounded bg-slate-800 text-teal-400 font-mono text-sm">\1</code>', text)
    
    # Bold: **text**
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong class="font-semibold text-white">\1</strong>', text)
    
    # Headings
    text = re.sub(r'^### (.*?)$', r'<h4 class="text-lg font-semibold text-teal-400 mt-6 mb-2">\1</h4>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'<h3 class="text-xl font-bold text-white mt-8 mb-3 border-b border-white/10 pb-1">\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.*?)$', r'<h2 class="text-2xl font-black text-white mt-10 mb-4 border-b-2 border-teal-500 pb-2">\1</h2>', text, flags=re.MULTILINE)
    
    # Bullet lists
    # Group list items together
    def format_list(match):
        items = match.group(0).split('\n')
        html_items = []
        for item in items:
            item_text = re.sub(r'^[-*]\s+', '', item)
            if item_text.strip():
                html_items.append(f'<li class="mb-1 text-slate-300 list-disc ml-5">{item_text}</li>')
        return '<ul class="my-3 space-y-1">' + ''.join(html_items) + '</ul>'
    
    text = re.sub(r'(?:^[-*]\s+.*?\n?)+', format_list, text, flags=re.MULTILINE)
    
    # Line breaks and paragraphs
    paragraphs = text.split('\n\n')
    for i, p in enumerate(paragraphs):
        if not p.strip() or p.startswith('<h') or p.startswith('<ul') or p.startswith('<!--CODE'):
            continue
        # Replace remaining newlines with break tags
        p_clean = p.replace('\n', '<br>')
        paragraphs[i] = f'<p class="text-slate-300 leading-relaxed my-3">{p_clean}</p>'
    
    text = '\n\n'.join(paragraphs)
    
    # Restore code blocks with PrismJS formatting
    for idx, (lang, code) in enumerate(code_blocks):
        escaped_code = html.escape(code)
        prism_html = (
            f'<div class="my-4 rounded-lg overflow-hidden border border-white/5 bg-[#1e1e1e] font-mono text-sm">'
            f'<div class="bg-[#181818] px-4 py-1.5 text-xs text-slate-400 border-b border-white/5 flex justify-between items-center">'
            f'<span>{lang.upper()}</span>'
            f'</div>'
            f'<pre class="language-{lang} p-4 overflow-x-auto"><code class="language-{lang}">{escaped_code}</code></pre>'
            f'</div>'
        )
        text = text.replace(f"<!--CODE_BLOCK_{idx}-->", prism_html)
        
    return text

def build_html_report(code_filepath, explanation, output_filepath):
    # Read the target code file
    try:
        with open(code_filepath, 'r', encoding='utf-8') as f:
            source_code = f.read()
    except Exception as e:
        print(f"Error reading code file {code_filepath}: {e}", file=sys.stderr)
        sys.exit(1)
        
    filename = os.path.basename(code_filepath)
    escaped_source_code = html.escape(source_code)
    
    # Format components
    overview_html = md_to_html(explanation.get('overview', ''))
    usage_html = md_to_html(explanation.get('usage', ''))
    rationale_html = md_to_html(explanation.get('rationale', ''))
    
    # Process walkthrough blocks
    walkthrough_items_html = ""
    walkthrough_blocks_js = []
    for idx, block in enumerate(explanation.get('walkthrough', [])):
        title = block.get('title', f'Block {idx+1}')
        lines = block.get('lines', '')
        content_html = md_to_html(block.get('content', ''))
        
        # Build line-highlight attribute/class targets
        start_line = 0
        end_line = 0
        if lines:
            nums = re.findall(r'\d+', lines)
            if len(nums) == 1:
                start_line = int(nums[0])
                end_line = int(nums[0])
            elif len(nums) >= 2:
                start_line = int(nums[0])
                end_line = int(nums[1])
        
        if start_line > 0:
            walkthrough_blocks_js.append(f"{{ start: {start_line}, end: {end_line}, id: 'walkthrough-card-{idx}' }}")
                
        walkthrough_items_html += f"""
        <div id="walkthrough-card-{idx}" class="walkthrough-card p-5 mb-4 rounded-xl border border-transparent bg-slate-900/40 hover:bg-slate-900/70 transition-all duration-300 cursor-pointer group"
             onmouseenter="hoverCard({start_line}, {end_line}, 'walkthrough-card-{idx}')"
             onmouseleave="clearHover()"
             onclick="scrollToLine({start_line})">
            <div class="flex justify-between items-center mb-2">
                <h4 class="text-base font-bold text-white group-hover:text-teal-400 transition-colors">{html.escape(title)}</h4>
                {f'<span class="px-2 py-0.5 rounded bg-teal-500/10 text-teal-400 font-mono text-xs border border-teal-500/20">{html.escape(lines)}</span>' if lines else ''}
            </div>
            <div class="text-sm text-slate-300 leading-relaxed">
                {content_html}
            </div>
        </div>
        """
        
    # Process Alternatives Comparison Matrix
    alt_rows_html = ""
    alt_cards_html = ""
    alternatives = explanation.get('alternatives', [])
    
    for idx, alt in enumerate(alternatives):
        name = alt.get('name', f'Alternative {idx+1}')
        metrics = alt.get('metrics', {})
        pros = alt.get('pros', [])
        cons = alt.get('cons', [])
        details_html = md_to_html(alt.get('details', ''))
        
        # Render stars/scores for table
        metrics_tds = ""
        for metric in ['Readability', 'Performance', 'Testability', 'Complexity']:
            val = metrics.get(metric, 3) # default 3
            # Render visual dots or stars
            dots = ""
            for d in range(1, 6):
                active_color = "bg-teal-500" if d <= val else "bg-slate-700"
                dots += f'<span class="inline-block w-2 h-2 rounded-full mx-0.5 {active_color}"></span>'
            metrics_tds += f"""
            <td class="px-6 py-4 text-center">
                <div class="flex justify-center items-center">{dots}</div>
            </td>
            """
            
        alt_rows_html += f"""
        <tr class="border-b border-white/5 hover:bg-slate-900/30 transition-colors">
            <td class="px-6 py-4 text-sm font-semibold text-white">{html.escape(name)}</td>
            {metrics_tds}
            <td class="px-6 py-4 text-right">
                <button onclick="toggleAltDetails({idx})" class="text-teal-400 hover:text-teal-300 font-medium text-xs transition-colors flex items-center justify-end gap-1 ml-auto">
                    <span>Details</span>
                    <svg id="alt-arrow-{idx}" class="w-3.5 h-3.5 transform transition-transform duration-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                    </svg>
                </button>
            </td>
        </tr>
        """
        
        # Accordion Detail Cards
        pros_li = "".join([f'<li class="flex items-start gap-2 text-slate-300 mb-1"><span class="text-emerald-500 font-bold">✓</span> {html.escape(p)}</li>' for p in pros])
        cons_li = "".join([f'<li class="flex items-start gap-2 text-slate-300 mb-1"><span class="text-rose-500 font-bold">✗</span> {html.escape(c)}</li>' for c in cons])
        
        alt_cards_html += f"""
        <div id="alt-details-card-{idx}" class="hidden mt-2 p-5 rounded-xl border border-white/10 bg-slate-900/50 backdrop-blur-md transition-all duration-300">
            <h4 class="text-lg font-bold text-white mb-3">{html.escape(name)} Analysis</h4>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div class="p-4 rounded-lg bg-emerald-500/5 border border-emerald-500/10">
                    <h5 class="text-sm font-bold text-emerald-400 mb-2">Pros / Strengths</h5>
                    <ul class="text-xs space-y-1">{pros_li}</ul>
                </div>
                <div class="p-4 rounded-lg bg-rose-500/5 border border-rose-500/10">
                    <h5 class="text-sm font-bold text-rose-400 mb-2">Cons / Limitations</h5>
                    <ul class="text-xs space-y-1">{cons_li}</ul>
                </div>
            </div>
            <div class="text-sm text-slate-300 border-t border-white/5 pt-3">
                {details_html}
            </div>
        </div>
        """

    # Visual/Mermaid Diagram setup
    mermaid_diagram = explanation.get('diagram', '')
    mermaid_block_html = ""
    if mermaid_diagram:
        # Wrap diagram inside a container
        mermaid_block_html = f"""
        <div class="mt-8 p-6 rounded-2xl border border-white/10 bg-slate-900/30">
            <h3 class="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <svg class="w-5 h-5 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
                <span>Visual Flow Diagram</span>
            </h3>
            <div class="mermaid flex justify-center py-4 bg-slate-950/40 rounded-xl border border-white/5 overflow-x-auto">
{mermaid_diagram}
            </div>
        </div>
        """

    # Build the full HTML output string
    html_content = f"""<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Explanation - {filename}</title>
    <!-- Tailwind CSS (v3) -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <!-- PrismJS Theme (Okaidia) -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-okaidia.min.css" rel="stylesheet">
    <!-- PrismJS Plugins (Line Numbers & Line Highlight) -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/line-numbers/prism-line-numbers.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/line-highlight/prism-line-highlight.min.css" rel="stylesheet">
    
    <style>
        body {{
            font-family: 'Outfit', sans-serif;
            background-color: #0b0f19;
        }}
        pre, code {{
            font-family: 'JetBrains Mono', monospace !important;
        }}
        .custom-scrollbar::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}
        .custom-scrollbar::-webkit-scrollbar-track {{
            background: rgba(255, 255, 255, 0.02);
        }}
        .custom-scrollbar::-webkit-scrollbar-thumb {{
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
        }}
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {{
            background: rgba(255, 255, 255, 0.2);
        }}
        /* Prism overrides */
        pre[class*="language-"] {{
            background: #111625 !important;
            margin: 0 !important;
            border-radius: 0 !important;
            border: none !important;
        }}
        /* Customize the native Prism line-highlight overlay color */
        .line-highlight {{
            background: rgba(20, 184, 166, 0.15) !important;
            border-left: 3px solid #14b8a6;
            pointer-events: none;
            z-index: 10;
        }}
        pre.has-highlight .line-highlight {{
            box-shadow: 0 0 0 9999px rgba(11, 15, 25, 0.75);
        }}
    </style>
</head>
<body class="h-full overflow-hidden text-slate-100 flex flex-col">

    <!-- Top Header Bar -->
    <header class="bg-slate-900/90 border-b border-white/10 px-6 py-4 flex-none flex items-center justify-between z-10 backdrop-blur-md">
        <div class="flex items-center gap-3">
            <div class="p-2 rounded-lg bg-teal-500/10 text-teal-400 border border-teal-500/20">
                <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
            </div>
            <div>
                <h1 class="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                    <span>Code Explanation:</span>
                    <span class="text-teal-400 font-mono text-lg">{html.escape(filename)}</span>
                </h1>
                <p class="text-xs text-slate-400 font-mono mt-0.5">{html.escape(code_filepath)}</p>
            </div>
        </div>
        <div class="flex items-center gap-4 text-xs font-mono text-slate-400">
            <div class="bg-slate-950/40 px-3 py-1.5 rounded-lg border border-white/5">
                Size: <span class="text-white font-semibold">{len(source_code)} bytes</span>
            </div>
            <div class="bg-slate-950/40 px-3 py-1.5 rounded-lg border border-white/5">
                Generated: <span class="text-white font-semibold">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
            </div>
        </div>
    </header>

    <!-- Split Workspace -->
    <main class="flex-1 flex overflow-hidden">
        
        <!-- Left Panel: Code view (50%) -->
        <section class="w-1/2 border-r border-white/10 flex flex-col bg-[#0b0f19] h-full overflow-hidden">
            <div class="bg-slate-950/60 border-b border-white/10 px-4 py-2 flex items-center justify-between">
                <span class="text-xs font-mono text-slate-400">Source Viewer</span>
                <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[10px]">Read-Only</span>
            </div>
            <div id="code-container" class="flex-1 overflow-y-auto custom-scrollbar p-0 relative">
                <pre id="pre-code-viewer" class="language-python line-numbers h-full"><code id="source-code-block" class="language-python">{escaped_source_code}</code></pre>
            </div>
        </section>

        <!-- Right Panel: Tabs & explanations (50%) -->
        <section class="w-1/2 flex flex-col bg-slate-950 h-full overflow-hidden">
            
            <!-- Tab Controls -->
            <div class="bg-slate-900/90 border-b border-white/10 flex-none px-4 flex items-center justify-between">
                <nav class="flex gap-2" aria-label="Tabs">
                    <button onclick="switchTab('tab-overview')" id="btn-tab-overview" class="px-4 py-4 text-sm font-semibold border-b-2 border-teal-500 text-teal-400">
                        Overview
                    </button>
                    <button onclick="switchTab('tab-walkthrough')" id="btn-tab-walkthrough" class="px-4 py-4 text-sm font-semibold border-b-2 border-transparent text-slate-400 hover:text-slate-200">
                        Walkthrough
                    </button>
                    <button onclick="switchTab('tab-usage')" id="btn-tab-usage" class="px-4 py-4 text-sm font-semibold border-b-2 border-transparent text-slate-400 hover:text-slate-200">
                        Usage Guide
                    </button>
                    <button onclick="switchTab('tab-rationale')" id="btn-tab-rationale" class="px-4 py-4 text-sm font-semibold border-b-2 border-transparent text-slate-400 hover:text-slate-200">
                        Rationale
                    </button>
                    <button onclick="switchTab('tab-alternatives')" id="btn-tab-alternatives" class="px-4 py-4 text-sm font-semibold border-b-2 border-transparent text-slate-400 hover:text-slate-200">
                        Alternatives
                    </button>
                </nav>
            </div>

            <!-- Tab Content Panel -->
            <div class="flex-1 overflow-y-auto custom-scrollbar p-6 bg-slate-950">
                
                <!-- Tab: Overview -->
                <div id="tab-overview" class="tab-panel space-y-4">
                    <div class="p-6 rounded-2xl bg-slate-900/40 border border-white/10 backdrop-blur-md">
                        {overview_html}
                    </div>
                </div>

                <!-- Tab: Walkthrough -->
                <div id="tab-walkthrough" class="tab-panel hidden space-y-4">
                    <div class="mb-4 text-sm text-slate-400 italic">
                        Tip: Click on a card to highlight the corresponding lines in the code panel.
                    </div>
                    {walkthrough_items_html}
                </div>

                <!-- Tab: Usage -->
                <div id="tab-usage" class="tab-panel hidden space-y-4">
                    <div class="p-6 rounded-2xl bg-slate-900/40 border border-white/10 backdrop-blur-md">
                        {usage_html}
                    </div>
                </div>

                <!-- Tab: Rationale -->
                <div id="tab-rationale" class="tab-panel hidden space-y-4">
                    <div class="p-6 rounded-2xl bg-slate-900/40 border border-white/10 backdrop-blur-md">
                        {rationale_html}
                    </div>
                </div>

                <!-- Tab: Alternatives -->
                <div id="tab-alternatives" class="tab-panel hidden space-y-6">
                    <!-- Matrix Table -->
                    <div class="overflow-x-auto rounded-2xl border border-white/10 bg-slate-900/30 backdrop-blur-md">
                        <table class="min-w-full divide-y divide-white/10">
                            <thead class="bg-slate-900/60">
                                <tr>
                                    <th scope="col" class="px-6 py-3.5 text-left text-xs font-bold uppercase tracking-wider text-slate-400">Approach</th>
                                    <th scope="col" class="px-6 py-3.5 text-center text-xs font-bold uppercase tracking-wider text-slate-400">Readability</th>
                                    <th scope="col" class="px-6 py-3.5 text-center text-xs font-bold uppercase tracking-wider text-slate-400">Performance</th>
                                    <th scope="col" class="px-6 py-3.5 text-center text-xs font-bold uppercase tracking-wider text-slate-400">Testability</th>
                                    <th scope="col" class="px-6 py-3.5 text-center text-xs font-bold uppercase tracking-wider text-slate-400">Complexity</th>
                                    <th scope="col" class="px-6 py-3.5 class text-right text-xs font-bold uppercase tracking-wider text-slate-400">Action</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-white/5">
                                {alt_rows_html}
                            </tbody>
                        </table>
                    </div>

                    <!-- Accordion card targets -->
                    <div class="space-y-4 mt-4">
                        {alt_cards_html}
                    </div>
                </div>

                <!-- Diagram blocks -->
                {mermaid_block_html}

            </div>
        </section>

    </main>

    <!-- PrismJS script loaders -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
    <!-- PrismJS Language Components -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-python.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-json.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-bash.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-sql.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-markdown.min.js"></script>
    <!-- PrismJS Plugins -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/line-numbers/prism-line-numbers.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/line-highlight/prism-line-highlight.min.js"></script>
    <!-- MermaidJS module loader -->
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});
    </script>

    <!-- Interactive JavaScript Logic -->
    <script>
        // Tab switching behavior
        function switchTab(tabId) {{
            // Hide all tab panels
            document.querySelectorAll('.tab-panel').forEach(panel => {{
                panel.classList.add('hidden');
            }});
            
            // Show selected panel
            document.getElementById(tabId).classList.remove('hidden');

            // Reset tab button states
            const buttons = [
                {{ btn: 'btn-tab-overview', id: 'tab-overview' }},
                {{ btn: 'btn-tab-walkthrough', id: 'tab-walkthrough' }},
                {{ btn: 'btn-tab-usage', id: 'tab-usage' }},
                {{ btn: 'btn-tab-rationale', id: 'tab-rationale' }},
                {{ btn: 'btn-tab-alternatives', id: 'tab-alternatives' }}
            ];

            buttons.forEach(item => {{
                const btnEl = document.getElementById(item.btn);
                if (item.id === tabId) {{
                    btnEl.classList.remove('border-transparent', 'text-slate-400');
                    btnEl.classList.add('border-teal-500', 'text-teal-400');
                }} else {{
                    btnEl.classList.remove('border-teal-500', 'text-teal-400');
                    btnEl.classList.add('border-transparent', 'text-slate-400');
                }}
            }});

            // Clear highlight if not on walkthrough
            if (tabId !== 'tab-walkthrough') {{
                const preElement = document.getElementById('pre-code-viewer');
                if (preElement) {{
                    preElement.removeAttribute('data-line');
                    preElement.classList.remove('has-highlight');
                    preElement.querySelectorAll('.line-highlight').forEach(el => el.remove());
                }}
            }}
        }}

        // Hover logic for bidirectional highlighting
        const walkthroughBlocks = [
            {', '.join(walkthrough_blocks_js)}
        ];

        let activeHoverCode = null;
        let activeHoverCard = null;

        function applyHighlight(startLine, endLine) {{
            const preElement = document.getElementById('pre-code-viewer');
            if (!preElement || !startLine) return;

            const range = startLine === endLine ? `${{startLine}}` : `${{startLine}}-${{endLine}}`;
            
            if (preElement.getAttribute('data-line') === range) return;

            preElement.querySelectorAll('.line-highlight').forEach(el => el.remove());
            preElement.setAttribute('data-line', range);
            preElement.classList.add('has-highlight');

            if (window.Prism && Prism.plugins && Prism.plugins.lineHighlight) {{
                Prism.plugins.lineHighlight.highlightLines(preElement)();
            }}
        }}

        function removeHighlight() {{
            const preElement = document.getElementById('pre-code-viewer');
            if (preElement) {{
                preElement.removeAttribute('data-line');
                preElement.classList.remove('has-highlight');
                preElement.querySelectorAll('.line-highlight').forEach(el => el.remove());
            }}
        }}

        function highlightCard(cardId) {{
            document.querySelectorAll('.walkthrough-card').forEach(card => {{
                if (card.id === cardId) {{
                    card.classList.add('border-teal-500/60', 'bg-slate-900/80');
                    card.classList.remove('border-transparent');
                }} else {{
                    card.classList.remove('border-teal-500/60', 'bg-slate-900/80');
                    card.classList.add('border-transparent');
                }}
            }});
        }}

        function resetCards() {{
            document.querySelectorAll('.walkthrough-card').forEach(card => {{
                card.classList.remove('border-teal-500/60', 'bg-slate-900/80');
                card.classList.add('border-transparent');
            }});
        }}

        function hoverCard(startLine, endLine, cardId) {{
            activeHoverCard = cardId;
            applyHighlight(startLine, endLine);
            highlightCard(cardId);
        }}

        function clearHover() {{
            activeHoverCard = null;
            if (!activeHoverCode) {{
                removeHighlight();
                resetCards();
            }} else {{
                // Restore code hover if we moved mouse from card but are still tracked in code
                const block = walkthroughBlocks.find(b => b.id === activeHoverCode);
                if (block) {{
                    applyHighlight(block.start, block.end);
                    highlightCard(block.id);
                }}
            }}
        }}

        function scrollToLine(startLine) {{
            if (!startLine) return;
            const preElement = document.getElementById('pre-code-viewer');
            const lineEl = preElement.querySelector(`.line-numbers-rows > span:nth-child(${{startLine}})`);
            if (lineEl) {{
                lineEl.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }}
        }}

        // Setup mousemove tracking on the code viewer
        document.addEventListener('DOMContentLoaded', () => {{
            const preElement = document.getElementById('pre-code-viewer');
            if (!preElement) return;

            preElement.addEventListener('mousemove', (e) => {{
                // estimate line number based on scroll and mouse position
                const rect = preElement.getBoundingClientRect();
                const style = window.getComputedStyle(preElement);
                const paddingTop = parseFloat(style.paddingTop) || 0;
                
                // Prism line-height is usually around 21px in Okaidia (1.5 line-height on 14px font)
                // Let's grab an actual line element if possible
                let lineHeight = 21; 
                const firstLine = preElement.querySelector('.line-numbers-rows > span');
                if (firstLine) {{
                    lineHeight = firstLine.getBoundingClientRect().height;
                }}

                const yOffset = e.clientY - rect.top + preElement.scrollTop - paddingTop;
                const hoveredLine = Math.floor(yOffset / lineHeight) + 1;

                if (hoveredLine > 0) {{
                    // Find if it belongs to a walkthrough block
                    const block = walkthroughBlocks.find(b => hoveredLine >= b.start && hoveredLine <= b.end);
                    if (block) {{
                        if (activeHoverCode !== block.id) {{
                            activeHoverCode = block.id;
                            if (!activeHoverCard) {{
                                applyHighlight(block.start, block.end);
                                highlightCard(block.id);
                            }}
                        }}
                    }} else {{
                        if (activeHoverCode !== null) {{
                            activeHoverCode = null;
                            if (!activeHoverCard) {{
                                removeHighlight();
                                resetCards();
                            }}
                        }}
                    }}
                }}
            }});

            preElement.addEventListener('mouseleave', () => {{
                activeHoverCode = null;
                if (!activeHoverCard) {{
                    removeHighlight();
                    resetCards();
                }}
            }});
        }});

        // Accordion behavior for alternatives
        function toggleAltDetails(index) {{
            const card = document.getElementById(`alt-details-card-${{index}}`);
            const arrow = document.getElementById(`alt-arrow-${{index}}`);
            
            if (card.classList.contains('hidden')) {{
                // Close others
                document.querySelectorAll('[id^="alt-details-card-"]').forEach(c => c.classList.add('hidden'));
                document.querySelectorAll('[id^="alt-arrow-"]').forEach(a => a.classList.remove('rotate-180'));
                
                card.classList.remove('hidden');
                arrow.classList.add('rotate-180');
            }} else {{
                card.classList.add('hidden');
                arrow.classList.remove('rotate-180');
            }}
        }}
    </script>
</body>
</html>
"""

    # Write HTML output file
    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Interactive report successfully written to {output_filepath}")
    except Exception as e:
        print(f"Error writing HTML report {output_filepath}: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Compile code files and explanation JSONs into interactive HTML reports.")
    parser.add_argument("--code-file", required=True, help="Path to the source code file.")
    parser.add_argument("--explanation-file", required=True, help="Path to the JSON file containing explanation content.")
    parser.add_argument("--output-file", required=True, help="Path to write the compiled HTML file.")
    parser.add_argument("--open", action="store_true", help="Automatically open the report in the default browser.")
    
    args = parser.parse_args()
    
    # Read explanation JSON
    try:
        with open(args.explanation_file, 'r', encoding='utf-8') as f:
            explanation = json.load(f)
    except Exception as e:
        print(f"Error reading explanation JSON {args.explanation_file}: {e}", file=sys.stderr)
        sys.exit(1)
        
    build_html_report(args.code_file, explanation, args.output_file)
    
    if args.open:
        print(f"Opening report in browser: {args.output_file}")
        webbrowser.open(f"file://{os.path.abspath(args.output_file)}")

if __name__ == "__main__":
    main()
