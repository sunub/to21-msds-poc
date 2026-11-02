"use strict";

// 승인된 9장. 내용은 UI_TEXT만 읽으며 요청 기록과 원문을 복사하지 않는다.
const HELP_CHAPTERS = {
  "flow": [
    [
      "p",
      "help.flow.purpose"
    ],
    [
      "ol",
      "help.flow.pdf",
      "help.flow.sections",
      "help.flow.extract",
      "help.flow.save",
      "help.flow.score"
    ],
    [
      "p",
      "help.flow.audience"
    ],
    [
      "p",
      "help.facts.run_name"
    ],
    [
      "p",
      "help.facts.run_example"
    ],
    [
      "p",
      "help.facts.run_conditions"
    ],
    [
      "p",
      "help.facts.journey"
    ],
    [
      "p",
      "help.facts.journey_read"
    ],
    [
      "p",
      "help.facts.journey_try"
    ],
    [
      "p",
      "help.facts.storage"
    ],
    [
      "p",
      "help.facts.cards"
    ]
  ],
  "score": [
    [
      "p",
      "help.score.weight"
    ],
    [
      "p",
      "help.score.target"
    ],
    [
      "p",
      "help.score.must"
    ],
    [
      "p",
      "help.facts.scores"
    ],
    [
      "p",
      "help.facts.targets"
    ],
    [
      "p",
      "help.facts.two_targets"
    ],
    [
      "p",
      "help.score.draft"
    ],
    [
      "p",
      "help.facts.ranking"
    ],
    [
      "p",
      "help.facts.empty_rows"
    ],
    [
      "p",
      "help.facts.auxiliary"
    ],
    [
      "p",
      "help.facts.draft_gap"
    ],
    [
      "p",
      "help.facts.old_draft"
    ],
    [
      "p",
      "help.facts.counts"
    ],
    [
      "p",
      "help.score.cause"
    ],
    [
      "ol",
      "help.facts.cause_conditions",
      "help.facts.cause_calls",
      "help.facts.cause_counts",
      "help.facts.cause_docs",
      "help.facts.cause_rows",
      "help.facts.cause_variation"
    ]
  ],
  "source": [
    [
      "p",
      "help.source.compare"
    ],
    [
      "p",
      "help.facts.source_select"
    ],
    [
      "p",
      "help.source.example"
    ],
    [
      "p",
      "help.source.no_fallback"
    ],
    [
      "p",
      "help.facts.source_estimated"
    ],
    [
      "p",
      "help.facts.source_colors"
    ]
  ],
  "setup": [
    [
      "p",
      "help.setup.read_offline"
    ],
    [
      "p",
      "help.setup.new_data"
    ],
    [
      "p",
      "help.setup.file_intro",
      "help.setup.filename",
      "help.setup.file_end"
    ],
    [
      "p",
      "help.setup.names_only"
    ],
    [
      "table",
      [
        "help.setup.name_column",
        "help.setup.meaning_column"
      ],
      [
        [
          "help.settings.runpod_url_name",
          "help.settings.runpod_url_meaning"
        ],
        [
          "help.settings.runpod_key_name",
          "help.settings.runpod_key_meaning"
        ],
        [
          "help.settings.company_url_name",
          "help.settings.company_url_meaning"
        ],
        [
          "help.settings.company_key_name",
          "help.settings.company_key_meaning"
        ],
        [
          "help.settings.management_key_name",
          "help.settings.management_key_meaning"
        ],
        [
          "help.settings.ssh_name",
          "help.settings.ssh_meaning"
        ]
      ]
    ],
    [
      "p",
      "help.settings.runpod_url_fact"
    ],
    [
      "p",
      "help.facts.rngd_tunnel"
    ],
    [
      "p",
      "help.facts.setup_copy"
    ],
    [
      "p",
      "help.setup.no_secrets"
    ],
    [
      "p",
      "help.setup.command_label"
    ],
    [
      "pre",
      "help.setup.command"
    ],
    [
      "p",
      "help.facts.setup_open"
    ],
    [
      "p",
      "help.facts.setup_reload"
    ]
  ],
  "retest": [
    [
      "p",
      "help.trial.meaning"
    ],
    [
      "ol",
      "help.facts.trial_scope",
      "help.facts.trial_ready",
      "help.facts.trial_practice",
      "help.facts.trial_send"
    ],
    [
      "table",
      [
        "common.progress",
        "common.content"
      ],
      [
        [
          "jobs.detail.input",
          "jobs.stages.input"
        ],
        [
          "jobs.detail.prompt",
          "jobs.stages.prompt"
        ],
        [
          "jobs.detail.raw_answer",
          "jobs.stages.raw_answer"
        ],
        [
          "jobs.detail.parsed",
          "jobs.stages.parsed"
        ],
        [
          "jobs.detail.converted",
          "jobs.stages.to21"
        ],
        [
          "jobs.detail.score",
          "jobs.stages.score"
        ]
      ]
    ],
    [
      "p",
      "help.facts.trial_many"
    ],
    [
      "p",
      "help.facts.jobs"
    ],
    [
      "details",
      "help.cli.title",
      [
        [
          "p",
          "help.cli.help_label"
        ],
        [
          "pre",
          "help.cli.help_command"
        ],
        [
          "p",
          "help.facts.cli_model"
        ],
        [
          "pre",
          "help.facts.cli_command"
        ],
        [
          "table",
          [
            "help.cli.option_column",
            "help.setup.meaning_column"
          ],
          [
            [
              "help.cli.section_flag",
              "help.cli.section_meaning"
            ],
            [
              "help.cli.all_flag",
              "help.cli.all_meaning"
            ],
            [
              "help.cli.dry_run_flag",
              "help.cli.dry_run_meaning"
            ],
            [
              "help.cli.system_file_flag",
              "help.cli.system_file_meaning"
            ],
            [
              "help.cli.base_run_flag",
              "help.cli.base_run_meaning"
            ],
            [
              "help.cli.show_prompt_flag",
              "help.cli.show_prompt_meaning"
            ],
            [
              "help.cli.json_flag",
              "help.cli.json_meaning"
            ]
          ]
        ],
        [
          "p",
          "help.facts.cli_repeat"
        ]
      ]
    ]
  ],
  "prompt": [
    [
      "p",
      "help.prompt.code_default"
    ],
    [
      "ul",
      "help.facts.prompt_spec",
      "help.facts.prompt_code",
      "help.facts.prompt_rows"
    ],
    [
      "p",
      "help.prompt.model_default"
    ],
    [
      "p",
      "help.prompt.trial_override"
    ],
    [
      "p",
      "help.facts.prompt_work"
    ],
    [
      "p",
      "help.facts.prompt_persist"
    ],
    [
      "p",
      "help.facts.prompt_version"
    ],
    [
      "p",
      "help.facts.prompt_private"
    ],
    [
      "p",
      "help.facts.prompt_temporary"
    ],
    [
      "p",
      "help.prompt.memory"
    ],
    [
      "p",
      "help.prompt.hash"
    ]
  ],
  "servers": [
    [
      "p",
      "help.servers.cost"
    ],
    [
      "p",
      "help.servers.states"
    ],
    [
      "p",
      "help.servers.waiting"
    ],
    [
      "p",
      "help.servers.company"
    ],
    [
      "p",
      "help.facts.server_confirmation"
    ],
    [
      "p",
      "help.facts.server_locked"
    ],
    [
      "p",
      "help.facts.server_owner"
    ],
    [
      "p",
      "help.facts.server_cost"
    ],
    [
      "p",
      "help.servers.manual_record"
    ],
    [
      "p",
      "help.facts.server_record"
    ]
  ],
  "recovery": [
    [
      "p",
      "help.recovery.length"
    ],
    [
      "p",
      "help.recovery.whitespace"
    ],
    [
      "p",
      "help.recovery.repetition"
    ],
    [
      "p",
      "help.facts.limit"
    ],
    [
      "p",
      "help.facts.limit_rule"
    ],
    [
      "p",
      "help.facts.limit_where"
    ],
    [
      "p",
      "help.recovery.columns"
    ],
    [
      "p",
      "help.facts.columns"
    ],
    [
      "p",
      "help.recovery.slow"
    ],
    [
      "p",
      "help.facts.slow"
    ],
    [
      "p",
      "help.recovery.connection"
    ],
    [
      "p",
      "help.facts.connection"
    ]
  ],
  "protection": [
    [
      "p",
      "help.protection.eval_locked"
    ],
    [
      "p",
      "help.facts.protect_eval"
    ],
    [
      "p",
      "help.protection.private_data"
    ],
    [
      "p",
      "help.protection.keys"
    ],
    [
      "p",
      "help.facts.protect_keys"
    ],
    [
      "p",
      "help.protection.delete_rented"
    ],
    [
      "p",
      "help.protection.tests"
    ],
    [
      "p",
      "help.facts.protect_tests"
    ],
    [
      "p",
      "help.protection.command_label"
    ],
    [
      "pre",
      "help.protection.command"
    ],
    [
      "p",
      "help.protection.harness_intro",
      "help.protection.docs_path",
      "help.protection.harness_end"
    ],
    [
      "p",
      "help.facts.protect_docs"
    ],
    [
      "p",
      "help.terms.distinction"
    ],
    [
      "p",
      "help.terms.section_count"
    ],
    [
      "p",
      "help.terms.criterion_count"
    ]
  ]
};
const HELP_CONTEXT = {s01: "score", s02: "source", s03: "retest", s04: "score",
  s05: "recovery", s06: "servers", s09: "retest", s10: "score"};
S.help = {topic: null, returnTo: null, lastScreen: null, pending: null, loaded: false,
  loading: false, glossaryError: null, criteriaError: null, criteria: null, search: ""};

function helpBlock(block) {
  const [tag, ...keys] = block;
  if (tag === "table") return h("table", null,
    h("thead", null, h("tr", null, keys[0].map(key => h("th", {scope: "col"}, T(key))))),
    h("tbody", null, keys[1].map(row => h("tr", null, row.map(key => h("td", null,
      key.endsWith("_name") || key.endsWith("_flag") ? h("code", {class: "technical"}, T(key)) : T(key)))))));
  if (tag === "details") return h("details", null, h("summary", null, T(keys[0])), keys[1].map(helpBlock));
  if (tag === "ul" || tag === "ol") return h(tag, null, keys.map(key => h("li", null, T(key))));
  return h(tag, tag === "pre" ? {class: "technical"} : null, keys.map(TKey => T(TKey)).join(" "));
}
function helpLink(topic, from) {
  return h("a", {href: `/static/guide.html#${topic}`, onclick: event => {
    event.preventDefault(); return helpOpen(topic, from, event.target);
  }}, T(`help.guide.${topic}.title`));
}
function helpRenderContext(screen) {
  const topic = HELP_CONTEXT[screen], el = document.getElementById(`help-context-${screen}`);
  if (topic && el) el.replaceChildren(h("span", null, T(`help.guide.${topic}.summary`)), " ", helpLink(topic, screen));
}
function helpOpen(topic, screen = S.shell.route, trigger = document.activeElement) {
  if (screen !== "s07") S.help.returnTo = {screen, focus: {...S.focus}, trigger};
  return go("s07", {helpTopic: Object.hasOwn(HELP_CHAPTERS, topic) ? topic : "flow"});
}
async function helpReturn() {
  const target = S.help.returnTo;
  if (!target) return go("s01");
  S.help.returnTo = null; S.focus = {...target.focus};
  await go(target.screen);
  if (target.trigger?.isConnected) target.trigger.focus();
  else document.getElementById(`title-${target.screen}`)?.focus();
}
function helpEnsure(args = {}) {
  if (Object.hasOwn(HELP_CHAPTERS, args.helpTopic)) S.help.topic = args.helpTopic;
  if (!S.help.loaded && !S.help.pending) return helpLoad();
  return S.help.pending || Promise.resolve();
}
function helpLoad(only = null) {
  if (S.help.pending) return S.help.pending;
  const H = S.help; H.loading = true; helpRenderTopics(); helpRenderGlossary();
  const work = (async () => {
    await Promise.all([!only || only === "terms" ? (async () => {
      try {
        const result = await api("/api/glossary");
        if (!Array.isArray(result.items) || !result.items.length || result.items.some(item =>
          !item || typeof item.term !== "string" || typeof item.short !== "string" ||
          typeof item.example !== "string" || !Array.isArray(item.also))) throw new Error("Invalid glossary response");
        S.glossary = result.items; H.glossaryError = null;
      } catch (error) { H.glossaryError = error; }
    })() : null, !only || only === "methods" ? (async () => {
      try {
        const result = await api("/api/criteria");
        if (!Array.isArray(result.items)) throw new Error("Invalid criteria response");
        H.criteria = result; H.criteriaError = null;
      } catch (error) { H.criteriaError = error; }
    })() : null]);
    H.loading = false; H.loaded = true; helpRenderGlossary(); helpRenderMethods();
  })();
  H.pending = work;
  return work.finally(() => {H.pending = null;});
}
function helpRenderTopics() {
  const el = document.getElementById("help-topics");
  const prior = new Map([...el.querySelectorAll("details[data-help-topic]")].map(d => [d.dataset.helpTopic, d.open]));
  el.classList.add("help-reading");
  coreReplace(el, h("p", null, T("help.title")),
    h("div", {class: "help-actions"},
      h("button", {id: "help-return", type: "button", onclick: helpReturn}, T("help.navigation.return")),
      h("button", {id: "help-replay", type: "button", onclick: () => emit("help_replay", {})}, T("help.replay_read"))),
    Object.entries(HELP_CHAPTERS).map(([topic, blocks]) => {
      const detail = h("details", {id: `help-${topic}`, "data-help-topic": topic},
        h("summary", null, T(`help.guide.${topic}.title`)),
        h("div", {class: "help-body"}, h("p", {class: "muted"}, T(`help.guide.${topic}.summary`)),
          blocks.map(helpBlock), topic === "score" ? h("details", {id: "help-method-details"},
            h("summary", null, T("help.score.open_methods")), h("div", {id: "help-methods"})) : null,
          h("p", null, h("a", {href: `/static/guide.html#${topic}`, target: "_blank", rel: "noopener"}, T("help.navigation.full")))));
      detail.open = topic === S.help.topic || prior.get(topic) === true;
      return detail;
    }));
  helpRenderMethods(); emit("journey_changed", {});
}
function helpRenderMethods() {
  const el = document.getElementById("help-methods"); if (!el) return;
  if (S.help.criteriaError) {
    el.replaceChildren(friendlyError({message: T("help.navigation.methods_failed"), fix: T("help.navigation.methods_todo"), raw: S.help.criteriaError.message}),
      h("button", {type: "button", id: "help-reload-methods", onclick: () => helpLoad("methods")}, T("help.navigation.methods_reload"))); return;
  }
  if (!S.help.criteria) {el.replaceChildren(h("p", {role: "status"}, T("help.navigation.loading"))); return;}
  const items = S.help.criteria.items;
  el.replaceChildren(h("table", null, h("thead", null, h("tr", null,
    ["common.item", "common.priority", "common.target", "score.criteria.method"].map(key => h("th", {scope: "col"}, T(key))))),
    h("tbody", null, items.map(item => {
      const key = Object.keys(UI.score.item_names).sort((a, b) => b.length - a.length).find(name => item.name.startsWith(name));
      return h("tr", null, h("td", null, key ? UI.score.item_names[key] : item.name),
        h("td", null, item.level), h("td", null, pct(item.target)), h("td", null, key ? UI.score.item_methods[key] : item.help));
    }))));
}
function helpRenderGlossary() {
  const el = document.getElementById("help-glossary"); el.classList.add("help-reading");
  const active = document.activeElement?.id;
  if (S.help.glossaryError) {
    el.replaceChildren(friendlyError({message: T("help.failed.title"), fix: T("help.failed.todo"), raw: S.help.glossaryError.message}),
      h("button", {id: "help-reload-terms", type: "button", onclick: () => helpLoad("terms")}, T("help.failed.reload"))); return;
  }
  if (!S.help.loaded && S.help.loading) {el.replaceChildren(h("p", {role: "status"}, T("help.navigation.loading"))); return;}
  const query = S.help.search.trim().toLocaleLowerCase();
  const items = S.glossary.filter(item => [item.term, item.short, ...item.also].some(value => value.toLocaleLowerCase().includes(query)));
  const input = h("input", {id: "help-search", type: "text", oninput: event => {S.help.search = event.target.value; helpRenderGlossary();}});
  input.value = S.help.search;
  coreReplace(el, h("h2", null, T("help.terms.title")), h("label", {for: "help-search"}, T("help.navigation.search")), input,
    h("dl", {class: "help-terms"}, items.map(item => [h("dt", {"data-glossary-term": item.term}, term(item.term)),
      h("dd", null, h("p", null, item.short), h("p", {class: "muted"}, item.example))])),
    !items.length ? h("p", {role: "status"}, T("help.navigation.empty")) : null);
  if (active === "help-search") input.focus({preventScroll: true});
}
on("screen_shown", ({screen}) => {
  helpRenderContext(screen);
  if (screen !== "s07") {S.help.lastScreen = screen; S.help.returnTo = null; S.help.topic = null; return;}
  if (!S.help.returnTo && S.help.lastScreen) {
    const focus = {...S.focus}; delete focus.helpTopic;
    S.help.returnTo = {screen: S.help.lastScreen, focus};
  }
  if (S.help.topic) {
    const detail = document.getElementById(`help-${S.help.topic}`);
    if (detail) {detail.open = true; detail.querySelector("summary").focus();}
  }
});
shellDefineView("help-topics", {load: helpEnsure, render: helpRenderTopics});
shellDefineView("help-glossary", {render: helpRenderGlossary});
