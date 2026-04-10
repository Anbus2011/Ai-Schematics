#!/usr/bin/env node
// Usage: node render.js <input.json> <output.svg> <skin.svg>
"use strict";

var fs = require("fs");
var netlistsvg = require("./built/index");

var args = process.argv.slice(2);
if (args.length < 3) {
    process.stderr.write("Usage: node render.js <input.json> <output.svg> <skin.svg>\n");
    process.exit(1);
}

var inputPath = args[0];
var outputPath = args[1];
var skinPath = args[2];

var skin = fs.readFileSync(skinPath, "utf-8");
var json = JSON.parse(fs.readFileSync(inputPath, "utf-8"));

netlistsvg.render(skin, json, function (err, svg) {
    if (err) {
        process.stderr.write(String(err));
        process.exit(1);
    }
    if (!svg) {
        process.stderr.write("netlistsvg returned empty output\n");
        process.exit(1);
    }
    fs.writeFileSync(outputPath, svg);
});
