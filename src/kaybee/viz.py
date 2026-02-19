"""Standalone visualization addon for KnowledgeGraph.

Generates self-contained interactive HTML with force-directed graph layout.
Obsidian-style graph with type hub nodes, rich hover cards, click-to-focus,
search, tag filters, and animated edges.

Usage::

    from kaybee.core import KnowledgeGraph
    from kaybee.viz import visualize

    kg = KnowledgeGraph()
    # ... populate ...
    html = visualize(kg)                    # returns HTML string
    visualize(kg, path="graph.html")        # also writes to file
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import KnowledgeGraph


_VIZ_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Knowledge Graph</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#1e1e2e;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#cdd6f4}
canvas{display:block;position:absolute;top:0;left:0}

/* Top bar */
#topbar{position:absolute;top:0;left:0;right:0;z-index:10;display:flex;align-items:center;gap:10px;padding:10px 14px;background:linear-gradient(180deg,#1e1e2eee 70%,#1e1e2e00)}
#search{background:#313244;color:#cdd6f4;border:1px solid #45475a;border-radius:8px;padding:7px 12px 7px 32px;font-size:13px;width:220px;outline:none;transition:border-color .2s}
#search:focus{border-color:#89b4fa}
#search-icon{position:absolute;left:24px;top:19px;color:#6c7086;font-size:13px;pointer-events:none}
.view-btn{background:#313244;color:#a6adc8;border:1px solid #45475a;border-radius:8px;padding:6px 14px;font-size:12px;cursor:pointer;transition:all .2s;user-select:none}
.view-btn:hover{border-color:#89b4fa;color:#cdd6f4}
.view-btn.active{background:#89b4fa22;border-color:#89b4fa;color:#89b4fa}
#node-count{color:#6c7086;font-size:11px;margin-left:auto}

/* Tag filter bar */
#tagbar{position:absolute;top:48px;left:14px;right:320px;z-index:10;display:flex;flex-wrap:wrap;gap:5px;padding:4px 0;max-height:60px;overflow:hidden}
.tag-chip{background:#31324488;color:#a6adc8;border:1px solid #45475a;border-radius:12px;padding:2px 10px;font-size:11px;cursor:pointer;transition:all .2s;user-select:none;white-space:nowrap}
.tag-chip:hover{border-color:#89b4fa;color:#cdd6f4}
.tag-chip.active{background:#89b4fa22;border-color:#89b4fa;color:#89b4fa}

/* Legend */
#legend{position:absolute;bottom:12px;left:12px;background:#313244dd;border:1px solid #45475a;border-radius:8px;padding:10px 14px;font-size:12px;z-index:10}
.legend-item{display:flex;align-items:center;gap:8px;margin:3px 0;cursor:pointer;transition:opacity .2s}
.legend-item:hover{opacity:0.8}
.legend-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0;box-shadow:0 0 6px var(--dot-color)}
.legend-label{opacity:0.85}
.legend-count{opacity:0.4;margin-left:auto;font-size:10px}

/* Hover card */
#hovercard{position:absolute;display:none;background:#313244f5;border:1px solid #45475a;border-radius:10px;padding:0;pointer-events:none;z-index:20;min-width:240px;max-width:320px;overflow:hidden;box-shadow:0 8px 32px #00000066}
#hc-header{padding:10px 14px 8px;border-bottom:1px solid #45475a33}
#hc-title{font-size:14px;font-weight:600;color:#cdd6f4}
#hc-type{font-size:11px;color:#89b4fa;margin-top:2px}
#hc-body{padding:8px 14px 10px}
#hc-desc{font-size:12px;color:#bac2de;line-height:1.5;margin-bottom:6px}
#hc-tags{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}
.hc-tag{background:#45475a55;border-radius:8px;padding:1px 8px;font-size:10px;color:#a6adc8}
#hc-stats{display:flex;gap:12px;font-size:11px;color:#6c7086}
.hc-stat{display:flex;align-items:center;gap:3px}
#hc-preview{font-size:11px;color:#7f849c;border-top:1px solid #45475a33;padding:8px 14px;max-height:60px;overflow:hidden;line-height:1.4}

/* Detail sidebar */
#sidebar{position:absolute;top:0;right:0;width:320px;height:100vh;background:#313244f0;border-left:1px solid #45475a;z-index:15;transform:translateX(100%);transition:transform .25s ease;overflow-y:auto;backdrop-filter:blur(12px)}
#sidebar.open{transform:translateX(0)}
#sb-close{position:absolute;top:10px;right:12px;background:none;border:none;color:#6c7086;font-size:18px;cursor:pointer;padding:4px 8px;border-radius:4px}
#sb-close:hover{color:#cdd6f4;background:#45475a44}
#sb-header{padding:16px 16px 12px;border-bottom:1px solid #45475a55}
#sb-title{font-size:18px;font-weight:700;color:#cdd6f4}
#sb-type-badge{display:inline-block;background:#89b4fa22;color:#89b4fa;border:1px solid #89b4fa44;border-radius:6px;padding:2px 10px;font-size:11px;margin-top:6px}
#sb-content{padding:14px 16px}
.sb-section{margin-bottom:14px}
.sb-section-title{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#6c7086;margin-bottom:6px;font-weight:600}
#sb-desc{font-size:13px;color:#bac2de;line-height:1.5}
#sb-tags{display:flex;flex-wrap:wrap;gap:5px}
.sb-tag{background:#45475a55;border-radius:8px;padding:2px 10px;font-size:11px;color:#a6adc8}
#sb-meta-list{font-size:12px;color:#bac2de}
.sb-meta-row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #45475a22}
.sb-meta-key{color:#6c7086}
.sb-meta-val{color:#cdd6f4;text-align:right;max-width:180px;overflow:hidden;text-overflow:ellipsis}
#sb-links-out,#sb-links-in{font-size:12px}
.sb-link{display:flex;align-items:center;gap:6px;padding:3px 0;color:#89b4fa;cursor:pointer;transition:color .15s}
.sb-link:hover{color:#b4d0fb}
.sb-link-arrow{color:#45475a;font-size:10px}
#sb-preview{font-size:12px;color:#7f849c;line-height:1.5;white-space:pre-wrap;background:#1e1e2e66;border-radius:6px;padding:10px;max-height:200px;overflow-y:auto}

/* Scrollbar */
#sidebar::-webkit-scrollbar{width:6px}
#sidebar::-webkit-scrollbar-track{background:transparent}
#sidebar::-webkit-scrollbar-thumb{background:#45475a;border-radius:3px}
</style>
</head>
<body>
<canvas id="c"></canvas>

<div id="topbar">
  <span id="search-icon">&#128269;</span>
  <input id="search" type="text" placeholder="Search nodes..." autocomplete="off"/>
  <button class="view-btn active" data-view="types">Types</button>
  <button class="view-btn" data-view="references">References</button>
  <button class="view-btn" data-view="tags">Tags</button>
  <span id="node-count"></span>
</div>

<div id="tagbar"></div>
<div id="legend"></div>

<div id="hovercard">
  <div id="hc-header"><div id="hc-title"></div><div id="hc-type"></div></div>
  <div id="hc-body">
    <div id="hc-desc"></div>
    <div id="hc-tags"></div>
    <div id="hc-stats"></div>
  </div>
  <div id="hc-preview"></div>
</div>

<div id="sidebar">
  <button id="sb-close">&times;</button>
  <div id="sb-header">
    <div id="sb-title"></div>
    <span id="sb-type-badge"></span>
  </div>
  <div id="sb-content">
    <div class="sb-section"><div class="sb-section-title">Description</div><div id="sb-desc"></div></div>
    <div class="sb-section"><div class="sb-section-title">Tags</div><div id="sb-tags"></div></div>
    <div class="sb-section"><div class="sb-section-title">Metadata</div><div id="sb-meta-list"></div></div>
    <div class="sb-section"><div class="sb-section-title">Outgoing Links</div><div id="sb-links-out"></div></div>
    <div class="sb-section"><div class="sb-section-title">Backlinks</div><div id="sb-links-in"></div></div>
    <div class="sb-section"><div class="sb-section-title">Content</div><div id="sb-preview"></div></div>
  </div>
</div>

<script>
(function(){
"use strict";

var DATA = __GRAPH_DATA__;
var PALETTE = ["#89b4fa","#a6e3a1","#f9e2af","#f38ba8","#cba6f7","#94e2d5","#fab387","#74c7ec","#f2cdcd","#eba0ac"];

var canvas = document.getElementById("c");
var ctx = canvas.getContext("2d");
var searchInput = document.getElementById("search");
var tagbarEl = document.getElementById("tagbar");
var legendEl = document.getElementById("legend");
var hovercardEl = document.getElementById("hovercard");
var sidebarEl = document.getElementById("sidebar");
var nodeCountEl = document.getElementById("node-count");
var W, H, dpr = window.devicePixelRatio || 1;

function resize(){
  W = window.innerWidth; H = window.innerHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  canvas.style.width = W + "px"; canvas.style.height = H + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
window.addEventListener("resize", resize);
resize();

/* ---------- Data structures ---------- */

var typeIndex = {};
for(var i = 0; i < DATA.types.length; i++) typeIndex[DATA.types[i]] = i;

/* Build node lookup — includes data nodes + synthetic type-hub nodes */
var nodeMap = {};
var nodes = [];
var typeHubs = {};

/* Create type hub nodes first */
for(var i = 0; i < DATA.types.length; i++){
  var tname = DATA.types[i];
  var count = 0;
  for(var j = 0; j < DATA.nodes.length; j++){
    if(DATA.nodes[j].type === tname) count++;
  }
  var hub = {
    id: "__type__" + tname,
    label: tname,
    type: tname,
    tags: [],
    isHub: true,
    childCount: count,
    description: count + " nodes",
    content: "",
    meta: {},
    outLinks: [],
    inLinks: [],
    x: W/2 + Math.cos(i * Math.PI * 2 / DATA.types.length) * Math.min(W, H) * 0.2,
    y: H/2 + Math.sin(i * Math.PI * 2 / DATA.types.length) * Math.min(W, H) * 0.2,
    vx: 0, vy: 0, pinned: false
  };
  nodes.push(hub);
  nodeMap[hub.id] = hub;
  typeHubs[tname] = hub;
}

/* Create entity nodes */
for(var i = 0; i < DATA.nodes.length; i++){
  var d = DATA.nodes[i];
  /* Position near their type hub */
  var hub = typeHubs[d.type];
  var cx = hub ? hub.x : W/2;
  var cy = hub ? hub.y : H/2;
  var n = {
    id: d.id, label: d.label, type: d.type, tags: d.tags || [],
    isHub: false,
    description: d.description || "",
    content: d.content || "",
    meta: d.meta || {},
    outLinks: d.out_links || [],
    inLinks: d.in_links || [],
    x: cx + (Math.random()-0.5) * 150,
    y: cy + (Math.random()-0.5) * 150,
    vx: 0, vy: 0, pinned: false
  };
  nodes.push(n);
  nodeMap[n.id] = n;
}

/* Build hub edges: type hub -> entity */
var hubEdges = [];
for(var i = 0; i < nodes.length; i++){
  var n = nodes[i];
  if(!n.isHub && n.type && typeHubs[n.type]){
    hubEdges.push({source: typeHubs[n.type], target: n, isHubEdge: true});
  }
}

/* Build wikilink edges */
var wikiEdges = [];
for(var i = 0; i < DATA.wikilink_edges.length; i++){
  var e = DATA.wikilink_edges[i];
  if(nodeMap[e.source] && nodeMap[e.target])
    wikiEdges.push({source: nodeMap[e.source], target: nodeMap[e.target]});
}

/* Compute degree */
var degree = {};
for(var i = 0; i < DATA.wikilink_edges.length; i++){
  var e = DATA.wikilink_edges[i];
  degree[e.source] = (degree[e.source]||0) + 1;
  degree[e.target] = (degree[e.target]||0) + 1;
}
var maxDeg = 1;
for(var k in degree) if(degree[k] > maxDeg) maxDeg = degree[k];

/* Compute tag edges */
var entityNodes = nodes.filter(function(n){ return !n.isHub; });
function buildTagEdges(){
  var edges = [];
  for(var i = 0; i < entityNodes.length; i++){
    for(var j = i+1; j < entityNodes.length; j++){
      var a = entityNodes[i], b = entityNodes[j];
      if(!a.tags.length || !b.tags.length) continue;
      var shared = [];
      for(var t = 0; t < a.tags.length; t++){
        if(b.tags.indexOf(a.tags[t]) >= 0) shared.push(a.tags[t]);
      }
      if(shared.length > 0) edges.push({source: a, target: b, weight: shared.length, sharedTags: shared});
    }
  }
  return edges;
}
var tagEdges = buildTagEdges();
var maxTagWeight = 1;
for(var i = 0; i < tagEdges.length; i++)
  if(tagEdges[i].weight > maxTagWeight) maxTagWeight = tagEdges[i].weight;

/* ---------- State ---------- */

var view = "types";
var camX = 0, camY = 0, zoom = 1;
var dragging = null, dragOffX = 0, dragOffY = 0, didDrag = false;
var panning = false, panStartX = 0, panStartY = 0, panCamX = 0, panCamY = 0;
var hovered = null;
var focused = null;   /* clicked node for sidebar */
var searchTerm = "";
var activeTags = {};  /* tag -> true */
var simRunning = true, simTicks = 0, SIM_SETTLE = 400;
var animTime = 0;
var particlePhase = 0;

function currentEdges(){
  if(view === "types") return hubEdges.concat(wikiEdges);
  if(view === "tags") return tagEdges;
  return wikiEdges;
}

/* ---------- Filtering ---------- */

function isNodeVisible(n){
  if(n.isHub) return view === "types";
  /* search filter */
  if(searchTerm){
    var s = searchTerm.toLowerCase();
    var match = n.label.toLowerCase().indexOf(s) >= 0;
    if(!match && n.description) match = n.description.toLowerCase().indexOf(s) >= 0;
    if(!match && n.tags.length){
      for(var t = 0; t < n.tags.length; t++){
        if(n.tags[t].toLowerCase().indexOf(s) >= 0){ match = true; break; }
      }
    }
    if(!match) return false;
  }
  /* tag filter */
  var activeTagList = Object.keys(activeTags);
  if(activeTagList.length > 0){
    var hasTag = false;
    for(var t = 0; t < activeTagList.length; t++){
      if(n.tags.indexOf(activeTagList[t]) >= 0){ hasTag = true; break; }
    }
    if(!hasTag) return false;
  }
  return true;
}

function getNeighbors(n){
  var edges = currentEdges();
  var neighbors = {};
  for(var i = 0; i < edges.length; i++){
    if(edges[i].source === n) neighbors[edges[i].target.id] = true;
    if(edges[i].target === n) neighbors[edges[i].source.id] = true;
  }
  return neighbors;
}

/* ---------- Rendering helpers ---------- */

function nodeRadius(n){
  if(n.isHub) return 18 + Math.sqrt(n.childCount) * 4;
  if(view === "references" || view === "types"){
    var d = degree[n.id] || 0;
    return 5 + (d / maxDeg) * 12;
  }
  return 7;
}

function nodeColor(n){
  if(n.type && typeIndex[n.type] !== undefined)
    return PALETTE[typeIndex[n.type] % PALETTE.length];
  return "#6c7086";
}

function hexToRgb(hex){
  var r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
  return {r:r, g:g, b:b};
}

/* ---------- Physics ---------- */

var REPULSION = 1200;
var HUB_REPULSION = 4000;
var SPRING_LEN = 90;
var HUB_SPRING_LEN = 120;
var SPRING_K = 0.004;
var DAMPING = 0.82;
var DT = 1;

function simulate(){
  if(!simRunning) return;
  var edges = currentEdges();
  var N = nodes.length;

  /* Repulsion */
  for(var i = 0; i < N; i++){
    if(nodes[i].pinned || !isNodeVisible(nodes[i])) continue;
    var fx = 0, fy = 0;
    var ni = nodes[i];
    for(var j = 0; j < N; j++){
      if(i === j || !isNodeVisible(nodes[j])) continue;
      var nj = nodes[j];
      var dx = ni.x - nj.x, dy = ni.y - nj.y;
      var dist2 = dx*dx + dy*dy;
      if(dist2 < 1) dist2 = 1;
      var rep = (ni.isHub || nj.isHub) ? HUB_REPULSION : REPULSION;
      var f = rep / dist2;
      var dist = Math.sqrt(dist2);
      fx += (dx / dist) * f;
      fy += (dy / dist) * f;
    }
    ni.vx += fx * DT;
    ni.vy += fy * DT;
  }

  /* Springs */
  for(var i = 0; i < edges.length; i++){
    var s = edges[i].source, t = edges[i].target;
    if(!isNodeVisible(s) || !isNodeVisible(t)) continue;
    var dx = t.x - s.x, dy = t.y - s.y;
    var dist = Math.sqrt(dx*dx + dy*dy) || 1;
    var restLen = edges[i].isHubEdge ? HUB_SPRING_LEN : SPRING_LEN;
    var f = (dist - restLen) * SPRING_K;
    var ffx = (dx / dist) * f, ffy = (dy / dist) * f;
    if(!s.pinned){ s.vx += ffx * DT; s.vy += ffy * DT; }
    if(!t.pinned){ t.vx -= ffx * DT; t.vy -= ffy * DT; }
  }

  /* Centering gravity */
  for(var i = 0; i < N; i++){
    if(nodes[i].pinned || !isNodeVisible(nodes[i])) continue;
    var gravity = nodes[i].isHub ? 0.001 : 0.0003;
    nodes[i].vx += (W/2 - nodes[i].x) * gravity;
    nodes[i].vy += (H/2 - nodes[i].y) * gravity;
  }

  /* Integrate */
  for(var i = 0; i < N; i++){
    if(nodes[i].pinned || !isNodeVisible(nodes[i])) continue;
    nodes[i].vx *= DAMPING;
    nodes[i].vy *= DAMPING;
    nodes[i].x += nodes[i].vx * DT;
    nodes[i].y += nodes[i].vy * DT;
  }

  simTicks++;
  if(simTicks > SIM_SETTLE){
    var totalV = 0, cnt = 0;
    for(var i = 0; i < N; i++){
      if(!isNodeVisible(nodes[i])) continue;
      totalV += Math.abs(nodes[i].vx) + Math.abs(nodes[i].vy);
      cnt++;
    }
    if(cnt > 0 && totalV / cnt < 0.05) simRunning = false;
  }
}

/* ---------- Camera transforms ---------- */

function toScreen(x, y){
  return {x: (x + camX) * zoom + W/2, y: (y + camY) * zoom + H/2};
}
function toWorld(sx, sy){
  return {x: (sx - W/2) / zoom - camX, y: (sy - H/2) / zoom - camY};
}

/* ---------- Drawing ---------- */

function drawEdge(x1, y1, x2, y2, r1, r2, color, alpha, lineWidth, showArrow, dashed){
  var dx = x2 - x1, dy = y2 - y1;
  var dist = Math.sqrt(dx*dx + dy*dy) || 1;
  var ux = dx/dist, uy = dy/dist;
  var sx = x1 + ux * r1, sy = y1 + uy * r1;
  var ex = x2 - ux * r2, ey = y2 - uy * r2;

  ctx.beginPath();
  if(dashed) ctx.setLineDash([4,4]);
  ctx.moveTo(sx, sy);
  ctx.lineTo(ex, ey);
  ctx.strokeStyle = color;
  ctx.globalAlpha = alpha;
  ctx.lineWidth = lineWidth;
  ctx.stroke();
  if(dashed) ctx.setLineDash([]);

  if(showArrow){
    var aLen = 7 * Math.max(1, lineWidth * 0.7), aW = 3.5 * Math.max(1, lineWidth * 0.5);
    ctx.beginPath();
    ctx.moveTo(ex, ey);
    ctx.lineTo(ex - ux*aLen + uy*aW, ey - uy*aLen - ux*aW);
    ctx.lineTo(ex - ux*aLen - uy*aW, ey - uy*aLen + ux*aW);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function drawParticle(x1, y1, x2, y2, r1, r2, color, phase){
  var dx = x2 - x1, dy = y2 - y1;
  var dist = Math.sqrt(dx*dx + dy*dy) || 1;
  var ux = dx/dist, uy = dy/dist;
  var sx = x1 + ux * r1, sy = y1 + uy * r1;
  var ex = x2 - ux * r2, ey = y2 - uy * r2;
  var t = phase % 1;
  var px = sx + (ex - sx) * t, py = sy + (ey - sy) * t;
  ctx.beginPath();
  ctx.arc(px, py, 2, 0, Math.PI*2);
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.8;
  ctx.fill();
  ctx.globalAlpha = 1;
}

function draw(){
  ctx.clearRect(0, 0, W, H);

  var edges = currentEdges();
  var focusNeighbors = focused ? getNeighbors(focused) : null;
  animTime += 0.005;
  particlePhase = animTime;

  var visibleCount = 0;

  /* Draw edges */
  for(var i = 0; i < edges.length; i++){
    var e = edges[i];
    var sVis = isNodeVisible(e.source), tVis = isNodeVisible(e.target);
    if(!sVis || !tVis) continue;

    var sp = toScreen(e.source.x, e.source.y);
    var tp = toScreen(e.target.x, e.target.y);
    var r1 = nodeRadius(e.source) * zoom;
    var r2 = nodeRadius(e.target) * zoom;
    var edgeColor = "#585b70";
    var alpha = 0.25;
    var lw = 1;
    var showArrow = (view === "references" || view === "types") && !e.isHubEdge;
    var dashed = !!e.isHubEdge;
    var isHighlighted = false;

    /* Focused: highlight neighborhood */
    if(focused){
      var involveFocus = (e.source === focused || e.target === focused);
      if(involveFocus){
        edgeColor = nodeColor(focused);
        alpha = 0.7;
        lw = 2;
        isHighlighted = true;
      } else {
        alpha = 0.06;
      }
    }

    /* Hovered highlight */
    if(!focused && hovered && (e.source === hovered || e.target === hovered)){
      edgeColor = nodeColor(hovered);
      alpha = 0.7;
      lw = 1.5;
      isHighlighted = true;
    }

    if(view === "tags" && !focused && !hovered){
      alpha = 0.1 + 0.4 * (e.weight || 1) / maxTagWeight;
      lw = 0.5 + 1.5 * (e.weight || 1) / maxTagWeight;
    }

    drawEdge(sp.x, sp.y, tp.x, tp.y, r1, r2, edgeColor, alpha, lw, showArrow, dashed);

    /* Animated particles on highlighted edges */
    if(isHighlighted && showArrow){
      var pPhase = (particlePhase + i * 0.37) % 1;
      drawParticle(sp.x, sp.y, tp.x, tp.y, r1, r2, edgeColor, pPhase);
      drawParticle(sp.x, sp.y, tp.x, tp.y, r1, r2, edgeColor, (pPhase + 0.5) % 1);
    }
  }

  /* Draw nodes */
  for(var i = 0; i < nodes.length; i++){
    var n = nodes[i];
    if(!isNodeVisible(n)) continue;
    visibleCount++;

    var p = toScreen(n.x, n.y);
    var r = nodeRadius(n) * zoom;
    var col = nodeColor(n);
    var rgb = hexToRgb(col);

    var isFocusNeighbor = focused && focusNeighbors && focusNeighbors[n.id];
    var dimmed = (focused && focused !== n && !isFocusNeighbor) ||
                 (hovered && hovered !== n && !focused &&
                  !(function(){ var ne = getNeighbors(hovered); return ne[n.id]; })());

    var nodeAlpha = dimmed ? 0.15 : 1;

    /* Glow for hubs or hovered */
    if((n.isHub || n === hovered || n === focused) && !dimmed){
      var glowR = r + (n.isHub ? 12 : 8);
      var grd = ctx.createRadialGradient(p.x, p.y, r * 0.5, p.x, p.y, glowR);
      grd.addColorStop(0, "rgba("+rgb.r+","+rgb.g+","+rgb.b+",0.3)");
      grd.addColorStop(1, "rgba("+rgb.r+","+rgb.g+","+rgb.b+",0)");
      ctx.beginPath();
      ctx.arc(p.x, p.y, glowR, 0, Math.PI*2);
      ctx.fillStyle = grd;
      ctx.fill();
    }

    /* Node circle */
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI*2);
    ctx.fillStyle = col;
    ctx.globalAlpha = nodeAlpha;
    ctx.fill();

    /* Ring for hubs */
    if(n.isHub){
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 2, 0, Math.PI*2);
      ctx.strokeStyle = col;
      ctx.globalAlpha = nodeAlpha * 0.5;
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    /* Focus ring */
    if(n === focused){
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 4, 0, Math.PI*2);
      ctx.strokeStyle = "#cdd6f4";
      ctx.globalAlpha = 0.6;
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    ctx.globalAlpha = 1;

    /* Labels */
    var showLabel = n.isHub || zoom > 0.45 || n === hovered || n === focused || isFocusNeighbor;
    if(showLabel && !dimmed){
      var fontSize = n.isHub ? Math.max(13, 15 * zoom) : Math.max(10, 11 * zoom);
      var fontWeight = (n.isHub || n === hovered || n === focused) ? "bold " : "";
      ctx.font = fontWeight + fontSize + "px -apple-system, BlinkMacSystemFont, sans-serif";
      ctx.fillStyle = "#cdd6f4";
      ctx.globalAlpha = n.isHub ? 0.95 : 0.85;
      ctx.textAlign = "center";
      ctx.fillText(n.label, p.x, p.y - r - 5 * zoom);
      ctx.globalAlpha = 1;
    } else if(dimmed && (n.isHub || zoom > 0.6)){
      var fontSize2 = n.isHub ? 12 : 10;
      ctx.font = fontSize2 + "px sans-serif";
      ctx.fillStyle = "#6c7086";
      ctx.globalAlpha = 0.2;
      ctx.textAlign = "center";
      ctx.fillText(n.label, p.x, p.y - r - 4 * zoom);
      ctx.globalAlpha = 1;
    }
  }

  /* Update count */
  var entityVis = visibleCount - (view === "types" ? DATA.types.length : 0);
  nodeCountEl.textContent = entityVis + " / " + DATA.nodes.length + " nodes";
}

/* ---------- UI: Legend ---------- */

function updateLegend(){
  if(DATA.types.length === 0){ legendEl.style.display = "none"; return; }
  legendEl.style.display = "block";
  var h = "";
  for(var i = 0; i < DATA.types.length; i++){
    var c = PALETTE[i % PALETTE.length];
    var count = 0;
    for(var j = 0; j < DATA.nodes.length; j++){
      if(DATA.nodes[j].type === DATA.types[i]) count++;
    }
    h += '<div class="legend-item" data-type="'+DATA.types[i]+'" style="--dot-color:'+c+'">';
    h += '<span class="legend-dot" style="background:'+c+'"></span>';
    h += '<span class="legend-label">'+DATA.types[i]+'</span>';
    h += '<span class="legend-count">'+count+'</span>';
    h += '</div>';
  }
  var untypedCount = 0;
  for(var j = 0; j < DATA.nodes.length; j++){
    if(!DATA.nodes[j].type) untypedCount++;
  }
  if(untypedCount > 0){
    h += '<div class="legend-item" style="--dot-color:#6c7086">';
    h += '<span class="legend-dot" style="background:#6c7086"></span>';
    h += '<span class="legend-label">untyped</span>';
    h += '<span class="legend-count">'+untypedCount+'</span>';
    h += '</div>';
  }
  legendEl.innerHTML = h;
}

/* ---------- UI: Tag bar ---------- */

function updateTagBar(){
  var h = "";
  for(var i = 0; i < DATA.all_tags.length; i++){
    var tag = DATA.all_tags[i];
    var cls = activeTags[tag] ? "tag-chip active" : "tag-chip";
    h += '<span class="'+cls+'" data-tag="'+tag+'">'+tag+'</span>';
  }
  tagbarEl.innerHTML = h;
}

tagbarEl.addEventListener("click", function(e){
  var chip = e.target.closest(".tag-chip");
  if(!chip) return;
  var tag = chip.getAttribute("data-tag");
  if(activeTags[tag]) delete activeTags[tag];
  else activeTags[tag] = true;
  updateTagBar();
  restartSim();
});

/* ---------- UI: Search ---------- */

searchInput.addEventListener("input", function(){
  searchTerm = this.value.trim();
  restartSim();
});

/* ---------- UI: View buttons ---------- */

document.querySelectorAll(".view-btn").forEach(function(btn){
  btn.addEventListener("click", function(){
    document.querySelectorAll(".view-btn").forEach(function(b){ b.classList.remove("active"); });
    this.classList.add("active");
    view = this.getAttribute("data-view");
    restartSim();
  });
});

/* ---------- UI: Hover card ---------- */

function showHoverCard(n, sx, sy){
  if(n.isHub){
    document.getElementById("hc-title").textContent = n.label;
    document.getElementById("hc-type").textContent = "Type Hub";
    document.getElementById("hc-desc").textContent = n.childCount + " nodes of this type";
    document.getElementById("hc-tags").innerHTML = "";
    document.getElementById("hc-stats").innerHTML = "";
    document.getElementById("hc-preview").textContent = "";
    document.getElementById("hc-preview").style.display = "none";
  } else {
    document.getElementById("hc-title").textContent = n.label;
    document.getElementById("hc-type").textContent = n.type || "untyped";
    document.getElementById("hc-desc").textContent = n.description || "";

    var tagsHtml = "";
    for(var t = 0; t < n.tags.length; t++){
      tagsHtml += '<span class="hc-tag">'+n.tags[t]+'</span>';
    }
    document.getElementById("hc-tags").innerHTML = tagsHtml;

    var deg = degree[n.id] || 0;
    document.getElementById("hc-stats").innerHTML =
      '<span class="hc-stat">&#8594; '+n.outLinks.length+'</span>' +
      '<span class="hc-stat">&#8592; '+n.inLinks.length+'</span>' +
      '<span class="hc-stat">&#9675; '+deg+' connections</span>';

    var preview = n.content;
    if(preview && preview.length > 120) preview = preview.substring(0, 120) + "...";
    var previewEl = document.getElementById("hc-preview");
    if(preview){
      previewEl.textContent = preview;
      previewEl.style.display = "block";
    } else {
      previewEl.style.display = "none";
    }
  }

  hovercardEl.style.display = "block";
  /* Position: keep within viewport */
  var cardW = 280, cardH = 200;
  var left = sx + 16;
  var top = sy + 16;
  if(left + cardW > W - 10) left = sx - cardW - 16;
  if(top + cardH > H - 10) top = sy - cardH - 16;
  if(left < 10) left = 10;
  if(top < 10) top = 10;
  hovercardEl.style.left = left + "px";
  hovercardEl.style.top = top + "px";
}

function hideHoverCard(){
  hovercardEl.style.display = "none";
}

/* ---------- UI: Sidebar ---------- */

function openSidebar(n){
  focused = n;
  sidebarEl.classList.add("open");

  if(n.isHub){
    document.getElementById("sb-title").textContent = n.label;
    document.getElementById("sb-type-badge").textContent = "Type Hub";
    document.getElementById("sb-type-badge").style.display = "inline-block";
    document.getElementById("sb-desc").textContent = n.childCount + " nodes of type '" + n.label + "'";
    document.getElementById("sb-tags").innerHTML = "";
    document.getElementById("sb-meta-list").innerHTML = "";

    /* List all child nodes as outgoing links */
    var childHtml = "";
    for(var i = 0; i < DATA.nodes.length; i++){
      if(DATA.nodes[i].type === n.label){
        childHtml += '<div class="sb-link" data-node="'+DATA.nodes[i].id+'"><span class="sb-link-arrow">&#9656;</span> '+DATA.nodes[i].id+'</div>';
      }
    }
    document.getElementById("sb-links-out").innerHTML = childHtml;
    document.getElementById("sb-links-in").innerHTML = "";
    document.getElementById("sb-preview").textContent = "";
    return;
  }

  document.getElementById("sb-title").textContent = n.label;
  if(n.type){
    document.getElementById("sb-type-badge").textContent = n.type;
    document.getElementById("sb-type-badge").style.display = "inline-block";
  } else {
    document.getElementById("sb-type-badge").style.display = "none";
  }

  document.getElementById("sb-desc").textContent = n.description || "(no description)";

  var tagsHtml = "";
  for(var t = 0; t < n.tags.length; t++){
    tagsHtml += '<span class="sb-tag">'+n.tags[t]+'</span>';
  }
  document.getElementById("sb-tags").innerHTML = tagsHtml || '<span style="color:#6c7086;font-size:11px">none</span>';

  /* Metadata */
  var metaHtml = "";
  var metaKeys = Object.keys(n.meta);
  for(var m = 0; m < metaKeys.length; m++){
    var k = metaKeys[m];
    if(k === "type" || k === "tags" || k === "description") continue;
    var v = n.meta[k];
    if(Array.isArray(v)) v = v.join(", ");
    metaHtml += '<div class="sb-meta-row"><span class="sb-meta-key">'+k+'</span><span class="sb-meta-val">'+v+'</span></div>';
  }
  document.getElementById("sb-meta-list").innerHTML = metaHtml || '<span style="color:#6c7086;font-size:11px">none</span>';

  /* Outgoing links */
  var outHtml = "";
  for(var i = 0; i < n.outLinks.length; i++){
    outHtml += '<div class="sb-link" data-node="'+n.outLinks[i]+'"><span class="sb-link-arrow">&#8594;</span> '+n.outLinks[i]+'</div>';
  }
  document.getElementById("sb-links-out").innerHTML = outHtml || '<span style="color:#6c7086;font-size:11px">none</span>';

  /* Backlinks */
  var inHtml = "";
  for(var i = 0; i < n.inLinks.length; i++){
    inHtml += '<div class="sb-link" data-node="'+n.inLinks[i]+'"><span class="sb-link-arrow">&#8592;</span> '+n.inLinks[i]+'</div>';
  }
  document.getElementById("sb-links-in").innerHTML = inHtml || '<span style="color:#6c7086;font-size:11px">none</span>';

  /* Content preview */
  document.getElementById("sb-preview").textContent = n.content || "(empty)";
}

function closeSidebar(){
  focused = null;
  sidebarEl.classList.remove("open");
}

document.getElementById("sb-close").addEventListener("click", closeSidebar);

/* Sidebar link clicks navigate to that node */
document.getElementById("sb-content").addEventListener("click", function(e){
  var link = e.target.closest(".sb-link");
  if(!link) return;
  var nodeId = link.getAttribute("data-node");
  var target = nodeMap[nodeId];
  if(target){
    openSidebar(target);
    /* Pan camera to target */
    camX = -target.x;
    camY = -target.y;
  }
});

/* ---------- Interaction ---------- */

function hitTest(sx, sy){
  var w = toWorld(sx, sy);
  /* Check hubs first (they're bigger targets) */
  for(var i = nodes.length - 1; i >= 0; i--){
    if(!isNodeVisible(nodes[i])) continue;
    var dx = nodes[i].x - w.x, dy = nodes[i].y - w.y;
    var r = nodeRadius(nodes[i]) / zoom + 5;
    if(dx*dx + dy*dy < r*r) return nodes[i];
  }
  return null;
}

function restartSim(){
  simRunning = true; simTicks = 0;
  for(var i = 0; i < nodes.length; i++){
    nodes[i].vx = (Math.random()-0.5)*1.5;
    nodes[i].vy = (Math.random()-0.5)*1.5;
    if(!dragging || nodes[i] !== dragging) nodes[i].pinned = false;
  }
}

canvas.addEventListener("mousedown", function(e){
  if(e.target !== canvas) return;
  var hit = hitTest(e.clientX, e.clientY);
  didDrag = false;
  if(hit){
    dragging = hit;
    dragging.pinned = true;
    var w = toWorld(e.clientX, e.clientY);
    dragOffX = hit.x - w.x;
    dragOffY = hit.y - w.y;
    simRunning = true; simTicks = 0;
  } else {
    panning = true;
    panStartX = e.clientX; panStartY = e.clientY;
    panCamX = camX; panCamY = camY;
  }
});

canvas.addEventListener("mousemove", function(e){
  if(dragging){
    var w = toWorld(e.clientX, e.clientY);
    dragging.x = w.x + dragOffX;
    dragging.y = w.y + dragOffY;
    dragging.vx = 0; dragging.vy = 0;
    didDrag = true;
  } else if(panning){
    var dx = e.clientX - panStartX, dy = e.clientY - panStartY;
    if(Math.abs(dx) > 3 || Math.abs(dy) > 3) didDrag = true;
    camX = panCamX + dx / zoom;
    camY = panCamY + dy / zoom;
  } else {
    var hit = hitTest(e.clientX, e.clientY);
    if(hit !== hovered){
      hovered = hit;
      if(hit) showHoverCard(hit, e.clientX, e.clientY);
      else hideHoverCard();
    } else if(hit){
      /* Update card position */
      var cardW = 280;
      var left = e.clientX + 16;
      if(left + cardW > W - 10) left = e.clientX - cardW - 16;
      if(left < 10) left = 10;
      hovercardEl.style.left = left + "px";
      hovercardEl.style.top = (e.clientY + 16) + "px";
    }
    canvas.style.cursor = hit ? "pointer" : "default";
  }
});

canvas.addEventListener("mouseup", function(e){
  if(dragging){
    if(!didDrag){
      /* Click without drag: open sidebar */
      openSidebar(dragging);
    }
    dragging.pinned = false;
    dragging = null;
  } else if(panning){
    if(!didDrag){
      /* Click on empty space: close sidebar */
      closeSidebar();
    }
    panning = false;
  }
});

canvas.addEventListener("wheel", function(e){
  e.preventDefault();
  var factor = e.deltaY < 0 ? 1.1 : 0.9;
  var oldZoom = zoom;
  zoom *= factor;
  zoom = Math.max(0.1, Math.min(zoom, 10));
  /* Zoom toward mouse position */
  var mx = e.clientX, my = e.clientY;
  camX += (mx - W/2) * (1/oldZoom - 1/zoom);
  camY += (my - H/2) * (1/oldZoom - 1/zoom);
}, {passive: false});

/* Escape key closes sidebar */
document.addEventListener("keydown", function(e){
  if(e.key === "Escape") closeSidebar();
  /* Ctrl/Cmd+F focuses search */
  if((e.ctrlKey || e.metaKey) && e.key === "f"){
    e.preventDefault();
    searchInput.focus();
    searchInput.select();
  }
});

/* ---------- Main loop ---------- */

function frame(){
  simulate();
  draw();
  requestAnimationFrame(frame);
}
updateLegend();
updateTagBar();
frame();
})();
</script>
</body>
</html>"""


def build_viz_data(kg: KnowledgeGraph) -> dict:
    """Extract visualization data from a KnowledgeGraph.

    Returns a dict with keys: ``nodes``, ``wikilink_edges``, ``types``, ``all_tags``.
    Each node includes description, content preview, metadata, outgoing and incoming links.
    """
    rows = kg._db.execute(
        "SELECT name, content, type, meta FROM nodes ORDER BY name"
    ).fetchall()

    # Build backlink map
    link_rows = kg._db.execute(
        "SELECT source_name, target_resolved FROM _links WHERE target_resolved IS NOT NULL"
    ).fetchall()
    backlink_map: dict[str, list[str]] = {}
    outlink_map: dict[str, list[str]] = {}
    for src, tgt in link_rows:
        outlink_map.setdefault(src, []).append(tgt)
        backlink_map.setdefault(tgt, []).append(src)

    nodes = []
    for name, content, typ, meta_json in rows:
        meta = json.loads(meta_json) if meta_json else {}
        node_tags = meta.get("tags", [])
        if not isinstance(node_tags, list):
            node_tags = []
        description = meta.get("description", "")
        content_preview = (content or "")[:300]

        nodes.append({
            "id": name,
            "label": name,
            "type": typ,
            "tags": node_tags,
            "description": description,
            "content": content_preview,
            "meta": {k: v for k, v in meta.items() if k not in ("type", "tags", "description")},
            "out_links": outlink_map.get(name, []),
            "in_links": backlink_map.get(name, []),
        })

    wikilink_edges = [{"source": src, "target": tgt} for src, tgt in link_rows]
    types = sorted({n["type"] for n in nodes if n["type"]})

    all_tags: set[str] = set()
    for n in nodes:
        all_tags.update(n["tags"])

    return {
        "nodes": nodes,
        "wikilink_edges": wikilink_edges,
        "types": types,
        "all_tags": sorted(all_tags),
    }


def visualize(kg: KnowledgeGraph, path: str | None = None) -> str:
    """Generate interactive HTML visualization of a KnowledgeGraph.

    Parameters
    ----------
    kg : KnowledgeGraph
        The graph to visualize.
    path : str, optional
        If given, write the HTML to this file path.

    Returns
    -------
    str
        The full self-contained HTML document.
    """
    data = build_viz_data(kg)
    data_json = json.dumps(data)
    html = _VIZ_HTML_TEMPLATE.replace("__GRAPH_DATA__", data_json)

    if path is not None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    return html
