const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('home page exposes the approved manual personal-data request channel', () => {
  for (const tree of ['public', 'docs']) {
    const html = fs.readFileSync(path.join(__dirname, '..', tree, 'index.html'), 'utf8');
    assert.match(html, /个人信息请求/);
    assert.match(html, /mailto:zimo66067@gmail\.com/);
    assert.match(html, /不要在邮件里发送密码、身份证或简历原文件/);
    assert.doesNotMatch(html, /查看原始密码|找回原始密码/);
  }
});
