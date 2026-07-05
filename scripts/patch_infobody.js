const fs = require('fs');

const file = 'D:\\MyCS\\AI\\Project\\LearnAnything\\web-vue\\src\\components\\GraphView.vue';
let content = fs.readFileSync(file, 'utf-8');

// 替换 info-body 部分
const oldInfoBody = `          <div class="info-body">
            <div class="info-section">
              <div class="info-label">ID</div>
              <div class="info-value mono">{{ selectedNode.id }}</div>
            </div>

            <div class="info-section">
              <div class="info-label">来源</div>
              <div class="info-value">{{ selectedNode.source || '—' }}</div>
            </div>

            <div class="info-section">
              <div class="info-label">页码</div>
              <div class="info-value">{{ selectedNode.page_number || '—' }}</div>
            </div>

            <div class="info-section">
              <div class="info-label">内容预览</div>
              <div class="info-text">{{ selectedNode.text || '（暂无内容）' }}</div>
            </div>

            <!-- 概念分解 -->`;

const newInfoBody = `          <div class="info-body">
            <!-- 概念节点详情 -->
            <template v-if="isConceptNode(selectedNode)">
              <div class="info-section">
                <div class="info-label">概念名称</div>
                <div class="info-value" style="font-size: 16px; font-weight: 600;">{{ selectedNode.label }}</div>
              </div>

              <div class="info-section">
                <div class="info-label">概念类型</div>
                <div class="info-value">
                  <span class="concept-badge" :class="'type-' + selectedNode.type">{{ typeLabel(selectedNode.type) }}</span>
                </div>
              </div>

              <div class="info-section">
                <div class="info-label">描述</div>
                <div class="info-text">{{ selectedNode.description || '（暂无描述）' }}</div>
              </div>

              <div class="info-section">
                <div class="info-label">来源</div>
                <div class="info-value mono">{{ selectedNode.source_chunks || '—' }}</div>
              </div>

              <div class="info-section">
                <div class="info-label">Parent Hint</div>
                <div class="info-value">{{ selectedNode.parent_hint || '（无）' }}</div>
              </div>

              <!-- 关联概念 -->
              <div class="info-section">
                <div class="info-label">关联概念</div>
                <div class="concept-links">
                  <div v-for="link in getNodeLinks(selectedNode.id)" :key="link.id" class="concept-link-item">
                    <span class="link-direction">{{ link.direction === 'out' ? '→' : '←' }}</span>
                    <span class="link-type" :class="'link-' + link.type">{{ link.type }}</span>
                    <span class="link-target">{{ link.targetName }}</span>
                  </div>
                  <div v-if="getNodeLinks(selectedNode.id).length === 0" class="concept-empty">暂无关联</div>
                </div>
              </div>
            </template>

            <!-- Chunk 节点详情 -->
            <template v-else>
              <div class="info-section">
                <div class="info-label">ID</div>
                <div class="info-value mono">{{ selectedNode.id }}</div>
              </div>

              <div class="info-section">
                <div class="info-label">来源</div>
                <div class="info-value">{{ selectedNode.source || '—' }}</div>
              </div>

              <div class="info-section">
                <div class="info-label">页码</div>
                <div class="info-value">{{ selectedNode.page_number || '—' }}</div>
              </div>

              <div class="info-section">
                <div class="info-label">内容预览</div>
                <div class="info-text">{{ selectedNode.text || '（暂无内容）' }}</div>
              </div>

              <!-- 概念分解 -->`;

content = content.replace(oldInfoBody, newInfoBody);

fs.writeFileSync(file, content);
console.log('Info body replaced');
