#! /usr/bin/env node
'use strict'
const { MegaLinterRunner } = require('../lib/index')
const assert = require('assert')

const release = process.env.MEGALINTER_RELEASE || 'insiders'
const nodockerpull = (process.env.MEGALINTER_NO_DOCKER_PULL === 'true') ? true : false

describe('Module', function () {
    it('(Module) run on own code base', async () => {
        const options = {
            path: './..',
            release,
            nodockerpull,
            debug: true
        }
        await new MegaLinterRunner().run(options)
        assert(process.exitCode === 0, `process.exitCode is 0 (${process.exitCode} returned)`)
    })
})