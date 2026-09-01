<template>
    <div class="config-layout">
        <div class="config-left page-card" style="align-self: flex-start">
            <div class="page-header">
                <div class="page-title-block">
                    <span class="page-title-icon"><Setting theme="filled" size="16" /></span>
                    <div>
                        <h2>LLM 配置</h2>
                        <p class="page-subtitle">模型连接与节点参数，保存后立即生效</p>
                    </div>
                </div>
                <el-tooltip content="重新显示首次进入系统时的配置引导" placement="bottom">
                    <el-button size="small" :loading="resettingSetup" @click="rerunSetupWizard">
                        <Magic theme="outline" size="14" class="btn-icon" />初始化引导
                    </el-button>
                </el-tooltip>
            </div>
            <input ref="fileInput" type="file" accept=".json" style="display:none" @change="onFileSelected" />
            <el-form :model="form" label-position="top" v-loading="loading" class="config-form">
                <section class="cfg-block">
                    <div class="form-grid">
                        <el-form-item label="协议">
                            <el-select v-model="form.protocol" @change="onGlobalProtocolChange">
                                <el-option label="OpenAI 兼容" value="openai" />
                                <el-option label="Anthropic" value="anthropic" />
                            </el-select>
                            <div class="field-hint">OpenAI 兼容：任意 /v1/chat/completions 端点；Anthropic：官方 /v1/messages 协议</div>
                        </el-form-item>
                        <el-form-item label="模型">
                            <el-input v-model="form.default_model" placeholder="gpt-4o-mini" />
                        </el-form-item>
                        <el-form-item label="API Key" class="grid-span-2">
                            <el-input v-model="form.api_key" type="password" show-password placeholder="sk-..." />
                        </el-form-item>
                        <el-form-item label="Base URL" class="grid-span-2">
                            <el-input v-model="form.base_url" :placeholder="baseUrlPlaceholder" />
                        </el-form-item>
                        <el-form-item label="默认温度">
                            <div class="inline-control">
                                <el-slider
                                    v-model="form.default_temperature"
                                    :min="0"
                                    :max="2"
                                    :step="0.1"
                                    :disabled="form.is_enable_thinking === 'enabled'"
                                />
                                <span
                                    class="node-val"
                                    :class="{ 'node-val-disabled': form.is_enable_thinking === 'enabled' }"
                                    >{{ form.default_temperature?.toFixed(1) }}</span
                                >
                            </div>
                            <div class="field-hint">思考模式开启时不生效</div>
                        </el-form-item>
                        <el-form-item label="默认 Token">
                            <el-input-number v-model="form.default_max_tokens" :min="256" :step="256" />
                            <div class="field-hint">节点未单独配置时的兜底上限</div>
                        </el-form-item>
                        <el-form-item label="思考模式">
                            <el-switch
                                v-model="form.is_enable_thinking"
                                active-value="enabled"
                                inactive-value="disabled"
                            />
                            <div class="field-hint">开启后忽略温度参数</div>
                        </el-form-item>
                        <el-form-item label="思考强度">
                            <el-select
                                v-model="form.default_reasoning_effort"
                                :disabled="form.is_enable_thinking !== 'enabled'"
                            >
                                <el-option label="low（轻度推理，更快更省）" value="low" />
                                <el-option label="medium（平衡）" value="medium" />
                                <el-option label="high（增强推理，默认）" value="high" />
                                <el-option label="max（深度推理，更慢更贵）" value="max" />
                            </el-select>
                            <div class="field-hint">仅思考模式开启时生效；medium 在 DeepSeek 上映射为 high</div>
                        </el-form-item>
                        <el-form-item label="最大上下文">
                            <el-input-number v-model="form.max_context_tokens" :min="0" :step="512" />
                            <div class="field-hint">发送给模型的提示词 token 上限（应用层估算裁剪），0 = 不裁剪</div>
                        </el-form-item>
                    </div>

                    <div class="form-actions">
                        <el-button type="primary" @click="save" :loading="saving" class="config-btn"
                            ><Save theme="outline" size="14" class="btn-icon" />保存配置</el-button
                        >
                        <el-button @click="test" :loading="testing" class="config-btn"
                            ><Link theme="outline" size="14" class="btn-icon" />测试连接</el-button
                        >
                    </div>
                </section>

                <section class="cfg-block">
                    <div class="section-head">
                        <span class="section-title"
                            ><Checklist theme="outline" size="15" class="section-icon" />功能开关</span
                        >
                        <span class="section-note">以下设置改动后即时保存</span>
                    </div>
                    <div class="form-grid">
                        <el-form-item label="玩家选择">
                            <el-switch
                                v-model="form.features.player_choice_enabled"
                                @change="saveFeatures"
                            />
                            <div class="field-hint">关闭后剧情将不再弹出玩家选择面板</div>
                        </el-form-item>
                        <el-form-item label="记忆间隔">
                            <el-input-number
                                v-model="form.features.memory_summarize_interval"
                                :min="1"
                                :step="1"
                                @change="saveFeatures"
                            />
                            <div class="field-hint">每隔 N 轮对话执行一次角色记忆总结</div>
                        </el-form-item>
                    </div>
                </section>
            </el-form>

            <div v-if="testResult" :class="['test-result', testResult.success ? 'test-success' : 'test-fail']">
                <div class="test-result-header">
                    <Check v-if="testResult.success" theme="filled" size="16" class="test-icon-success" />
                    <Caution v-else theme="filled" size="16" class="test-icon-fail" />
                    <span class="test-status">{{ testResult.success ? "连接成功" : "连接失败" }}</span>
                    <span class="test-elapsed">{{ testResult.elapsed_ms }}ms</span>
                </div>
                <div v-if="testResult.success" class="test-response">
                    <strong>模型回复：</strong>{{ testResult.response }}
                </div>
                <div v-else class="test-error">
                    {{ testResult.error }}
                </div>
            </div>

            <el-collapse v-model="activeCollapse" class="cfg-collapse" style="margin-top: 20px" @change="onCollapseChange">
                <el-collapse-item name="nodes">
                    <template #title>
                        <span class="cfg-collapse-title"
                            ><SettingTwo theme="outline" size="15" class="cfg-collapse-icon" />节点参数配置</span
                        ><span class="cfg-collapse-sub">逐节点参数与独立 LLM 接口</span>
                    </template>
                    <p class="collapse-hint">
                        为每个节点单独配置温度、最大 Token、思考模式、思考强度与最大上下文，以及独立的 LLM
                        接口（API Key / Base URL / 模型 / 超时）。节点级 LLM 留空即继承全局配置，填写后优先于全局。
                    </p>
                    <div v-for="nd in NODE_DEFS" :key="nd.id" class="node-card">
                        <div class="node-card-title">
                            <component :is="nodeIcon(nd.id)" theme="outline" size="15" class="node-card-icon" />
                            {{ nd.label }}<span class="node-card-id">({{ nd.id }})</span>
                        </div>
                        <el-form label-position="top" size="small" class="node-params-form">
                            <div class="form-grid">
                                <el-form-item label="温度">
                                    <div class="inline-control">
                                        <el-slider
                                            v-model="nodeParams[nd.id].temperature"
                                            :min="0"
                                            :max="2"
                                            :step="0.1"
                                            :disabled="nodeParams[nd.id].is_enable_thinking === 'enabled'"
                                        />
                                        <span
                                            class="node-val"
                                            :class="{ 'node-val-disabled': nodeParams[nd.id].is_enable_thinking === 'enabled' }"
                                            >{{ nodeParams[nd.id]?.temperature?.toFixed(1) }}</span
                                        >
                                    </div>
                                </el-form-item>
                                <el-form-item label="最大 Token">
                                    <el-input-number v-model="nodeParams[nd.id].max_tokens" :min="256" :step="256" />
                                </el-form-item>
                                <el-form-item label="思考模式">
                                    <el-switch
                                        v-model="nodeParams[nd.id].is_enable_thinking"
                                        active-value="enabled"
                                        inactive-value="disabled"
                                    />
                                </el-form-item>
                                <el-form-item label="思考强度">
                                    <el-select
                                        v-model="nodeParams[nd.id].reasoning_effort"
                                        clearable
                                        placeholder="继承全局"
                                        :disabled="nodeParams[nd.id].is_enable_thinking !== 'enabled'"
                                    >
                                        <el-option label="low" value="low" />
                                        <el-option label="medium" value="medium" />
                                        <el-option label="high" value="high" />
                                        <el-option label="max" value="max" />
                                    </el-select>
                                </el-form-item>
                                <el-form-item label="最大上下文" class="grid-span-2">
                                    <el-input-number
                                        v-model="nodeParams[nd.id].max_context_tokens"
                                        :min="0"
                                        :step="512"
                                    />
                                    <div class="field-hint">0 = 继承全局</div>
                                </el-form-item>
                            </div>
                        </el-form>

                        <div class="node-llm">
                            <div class="node-llm-head">
                                <el-switch v-model="nodeLlmOn[nd.id]" size="small" />
                                <span class="node-llm-title">
                                    <Api theme="outline" size="14" class="node-llm-icon" />独立 LLM 接口
                                </span>
                                <span class="node-llm-note">
                                    {{
                                        nodeLlmOn[nd.id]
                                            ? "仅覆盖已填字段，留空继承全局"
                                            : "当前继承全局 LLM 配置"
                                    }}
                                </span>
                            </div>
                            <el-form v-if="nodeLlmOn[nd.id]" label-position="top" size="small" class="node-llm-form">
                                <div class="form-grid">
                                    <el-form-item label="协议">
                                        <el-select
                                            v-model="nodeLlm[nd.id].protocol"
                                            clearable
                                            placeholder="继承全局"
                                        >
                                            <el-option label="OpenAI 兼容" value="openai" />
                                            <el-option label="Anthropic" value="anthropic" />
                                        </el-select>
                                    </el-form-item>
                                    <el-form-item label="模型">
                                        <el-input
                                            v-model="nodeLlm[nd.id].default_model"
                                            :placeholder="nodeLlmPlaceholder('default_model')"
                                        />
                                    </el-form-item>
                                    <el-form-item label="API Key" class="grid-span-2">
                                        <el-input
                                            v-model="nodeLlm[nd.id].api_key"
                                            type="password"
                                            show-password
                                            :placeholder="nodeLlmPlaceholder('api_key')"
                                        />
                                    </el-form-item>
                                    <el-form-item label="Base URL" class="grid-span-2">
                                        <el-input
                                            v-model="nodeLlm[nd.id].base_url"
                                            :placeholder="nodeLlmPlaceholder('base_url')"
                                        />
                                    </el-form-item>
                                    <el-form-item label="超时(秒)">
                                        <el-input-number
                                            v-model="nodeLlm[nd.id].timeout_seconds"
                                            :min="1"
                                            :step="30"
                                            :placeholder="nodeLlmPlaceholder('timeout_seconds')"
                                        />
                                    </el-form-item>
                                    <el-form-item label="思考强度">
                                        <el-select
                                            v-model="nodeLlm[nd.id].default_reasoning_effort"
                                            clearable
                                            placeholder="继承全局"
                                        >
                                            <el-option label="low" value="low" />
                                            <el-option label="medium" value="medium" />
                                            <el-option label="high" value="high" />
                                            <el-option label="max" value="max" />
                                        </el-select>
                                    </el-form-item>
                                    <el-form-item label="最大上下文" class="grid-span-2">
                                        <el-input-number
                                            v-model="nodeLlm[nd.id].max_context_tokens"
                                            :min="0"
                                            :step="512"
                                            :placeholder="nodeLlmPlaceholder('max_context_tokens')"
                                        />
                                        <div class="field-hint">0 = 不裁剪</div>
                                    </el-form-item>
                                </div>
                                <div class="node-llm-actions">
                                    <el-button
                                        size="small"
                                        text
                                        type="primary"
                                        :loading="nodeLlmTesting === nd.id"
                                        @click="testNodeLlm(nd.id)"
                                        >测试连接</el-button
                                    >
                                    <el-button size="small" text @click="clearNodeLlm(nd.id)"
                                        >清空并继承全局</el-button
                                    >
                                </div>
                                <div
                                    v-if="nodeLlmTestResult[nd.id]"
                                    :class="[
                                        'node-llm-result',
                                        nodeLlmTestResult[nd.id].success ? 'node-llm-ok' : 'node-llm-fail'
                                    ]"
                                >
                                    <template v-if="nodeLlmTestResult[nd.id].success">
                                        连接成功（{{ nodeLlmTestResult[nd.id].elapsed_ms }}ms）：{{
                                            nodeLlmTestResult[nd.id].response
                                        }}
                                    </template>
                                    <template v-else>{{ nodeLlmTestResult[nd.id].error }}</template>
                                </div>
                            </el-form>
                        </div>

                        <div class="node-card-actions">
                            <el-button size="small" text type="primary" @click="editPrompt(nd)"
                                ><EditOne theme="outline" size="14" /> 编辑系统提示词
                                <span v-if="promptDirty.has(nd.id)" class="prompt-unsaved-dot" title="有未保存的改动"></span
                            ></el-button>
                        </div>
                    </div>
                    <div class="collapse-actions">
                        <span v-if="promptDirty.size" class="unsaved-hint"
                            >有 {{ promptDirty.size }} 个节点的提示词未保存</span
                        >
                        <el-button type="primary" @click="saveNodeParams" :loading="savingNodes"
                            ><Save theme="outline" size="14" class="btn-icon" />保存节点参数</el-button
                        >
                        <el-button @click="handleExportConfig"
                            ><Download theme="outline" size="14" class="btn-icon" />导出节点配置</el-button
                        >
                        <el-button type="success" plain @click="triggerImportConfig"
                            ><Upload theme="outline" size="14" class="btn-icon" />导入节点配置</el-button
                        >
                    </div>
                </el-collapse-item>
                <el-collapse-item name="system_rules">
                    <template #title>
                        <span class="cfg-collapse-title"
                            ><Caution theme="outline" size="15" class="cfg-collapse-icon" />系统限制（共享）</span
                        ><span class="cfg-collapse-sub">追加到全部节点提示词末尾</span>
                    </template>
                    <p class="collapse-hint">
                        这段内容会自动追加到所有节点系统提示词的末尾。修改后下次对话生效；仓库不内置任何规则，留空即不追加任何内容。填写后保存在本地
                        config.json（已排除版本控制），不会随仓库分发。
                    </p>
                    <el-input
                        v-model="systemRules"
                        type="textarea"
                        :rows="10"
                        placeholder="输入系统限制内容..."
                        class="prompt-textarea"
                    />
                    <div class="collapse-actions">
                        <el-button type="primary" @click="saveSystemRules" :loading="savingRules"
                            ><Save theme="outline" size="14" class="btn-icon" />保存系统限制</el-button
                        >
                        <el-button @click="resetSystemRules">清空</el-button>
                    </div>
                </el-collapse-item>
                <el-collapse-item name="node_contexts">
                    <template #title>
                        <span class="cfg-collapse-title"
                            ><MindMapping theme="outline" size="15" class="cfg-collapse-icon" />上下文注入配置</span
                        ><span class="cfg-collapse-sub">上下文块的选择与顺序</span>
                    </template>
                    <p class="collapse-hint">
                        配置每个节点注入哪些上下文块（对话历史 / 世界观 / 记忆 / 关系 / 情绪等）及顺序。
                        块按顺序追加在提示词正文之后、全局系统限制之前；修改后下次对话生效。
                    </p>
                    <div class="ctx-node-row">
                        <span class="ctx-node-label">节点</span>
                        <el-select v-model="ctxNode" size="small" style="width: 240px">
                            <el-option v-for="nd in CTX_NODE_OPTIONS" :key="nd.id" :label="nd.label" :value="nd.id" />
                        </el-select>
                        <el-button size="small" @click="resetCtxNode">恢复默认</el-button>
                    </div>
                    <div class="ctx-blocks">
                        <div v-for="(b, i) in ctxCurrent" :key="i" class="ctx-block-row">
                            <span class="ctx-block-order">{{ i + 1 }}</span>
                            <span class="ctx-block-title">{{ ctxTitle(b) }}</span>
                            <span class="ctx-block-id">{{ b.id }}</span>
                            <el-button size="small" text :disabled="i === 0" @click="moveCtx(i, -1)"
                                ><ArrowUp theme="outline" size="13"
                            /></el-button>
                            <el-button size="small" text :disabled="i === ctxCurrent.length - 1" @click="moveCtx(i, 1)"
                                ><Down theme="outline" size="13"
                            /></el-button>
                            <el-button size="small" text type="danger" @click="removeCtx(i)"
                                ><Close theme="outline" size="13"
                            /></el-button>
                        </div>
                        <div v-if="!ctxCurrent.length" class="ctx-empty">该节点未配置上下文块</div>
                    </div>
                    <div class="ctx-add-row">
                        <el-select
                            v-model="ctxAddId"
                            size="small"
                            placeholder="添加上下文块..."
                            filterable
                            style="width: 240px"
                        >
                            <el-option
                                v-for="bl in ctxAddable"
                                :key="bl.id"
                                :label="bl.title"
                                :value="bl.id"
                            />
                        </el-select>
                        <el-button size="small" type="primary" plain @click="addCtx">添加</el-button>
                    </div>
                    <div class="collapse-actions">
                        <span v-if="ctxDirty" class="unsaved-hint">上下文配置有未保存的改动</span>
                        <el-button type="primary" @click="saveNodeContexts" :loading="savingCtx"
                            ><Save theme="outline" size="14" class="btn-icon" />保存上下文配置</el-button
                        >
                    </div>
                </el-collapse-item>
                <el-collapse-item name="image_gen">
                    <template #title>
                        <span class="cfg-collapse-title"
                            ><Camera theme="outline" size="15" class="cfg-collapse-icon" />场景插画配置 (ComfyUI)</span
                        ><span class="cfg-collapse-sub">服务地址、画面与生成节奏</span>
                    </template>
                    <p class="collapse-hint">
                        ComfyUI 为独立服务，请自行启动后在此配置服务地址；插画关闭或服务离线时不会影响叙事流程。
                    </p>
                    <div class="ig-connection">
                        <div class="ig-conn-row">
                            <span class="ig-conn-label">启用插画</span>
                            <el-switch v-model="imageGeneration.enabled" />
                            <span class="field-hint">开启后每回合按冷却间隔与数量上限生成场景插画</span>
                        </div>
                        <div class="ig-conn-row">
                            <span class="ig-conn-label">服务地址</span>
                            <el-input
                                v-model="imageGeneration.comfyui_base_url"
                                placeholder="http://127.0.0.1:8188"
                                class="ig-conn-input"
                            />
                            <el-button @click="testComfyui" :loading="testingComfyui"
                                ><Link theme="outline" size="14" class="btn-icon" />测试连接</el-button
                            >
                        </div>
                        <div class="ig-conn-actions">
                            <el-button type="primary" @click="saveImageGenConfig" :loading="savingImageGen"
                                ><Save theme="outline" size="14" class="btn-icon" />保存插画配置</el-button
                            >
                        </div>
                    </div>
                    <div
                        v-if="comfyuiTestResult"
                        :class="['test-result', comfyuiTestResult.success ? 'test-success' : 'test-fail']"
                    >
                        <div class="test-result-header">
                            <Check v-if="comfyuiTestResult.success" theme="filled" size="16" class="test-icon-success" />
                            <Caution v-else theme="filled" size="16" class="test-icon-fail" />
                            <span class="test-status">{{ comfyuiTestResult.success ? "连接成功" : "连接失败" }}</span>
                            <span class="test-elapsed">{{ comfyuiTestResult.elapsed_ms }}ms</span>
                        </div>
                        <div v-if="comfyuiTestResult.success" class="test-response">
                            <strong>可用模型：</strong>{{ checkpointOptions.length ? `共 ${checkpointOptions.length} 个，可在下方选择` : "未获取到模型列表（不影响连接）" }}
                        </div>
                        <div v-else class="test-error">
                            {{ comfyuiTestResult.error }}
                        </div>
                    </div>
                    <div class="ig-field ig-mt">
                        <span class="ig-label">checkpoint</span>
                        <el-select
                            v-model="imageGeneration.checkpoint"
                            filterable
                            allow-create
                            default-first-option
                            placeholder="测试连接后选择，或直接输入模型文件名"
                            class="ig-num"
                        >
                            <el-option v-for="c in checkpointOptions" :key="c" :label="c" :value="c" />
                        </el-select>
                    </div>
                    <div class="ig-group-title">画面与采样</div>
                    <div class="ig-grid">
                        <div class="ig-field">
                            <span class="ig-label">画面宽度</span>
                            <el-input-number
                                v-model="imageGeneration.width"
                                :min="64"
                                :step="64"
                                controls-position="right"
                                class="ig-num"
                            />
                        </div>
                        <div class="ig-field">
                            <span class="ig-label">画面高度</span>
                            <el-input-number
                                v-model="imageGeneration.height"
                                :min="64"
                                :step="64"
                                controls-position="right"
                                class="ig-num"
                            />
                        </div>
                        <div class="ig-field">
                            <span class="ig-label">生成步数</span>
                            <el-input-number
                                v-model="imageGeneration.steps"
                                :min="1"
                                :step="5"
                                controls-position="right"
                                class="ig-num"
                            />
                        </div>
                        <div class="ig-field">
                            <span class="ig-label">CFG 引导系数</span>
                            <el-input-number
                                v-model="imageGeneration.cfg"
                                :min="0.1"
                                :step="0.5"
                                controls-position="right"
                                class="ig-num"
                            />
                        </div>
                        <div class="ig-field">
                            <span class="ig-label">采样器</span>
                            <el-select
                                v-model="imageGeneration.sampler_name"
                                filterable
                                allow-create
                                default-first-option
                                class="ig-num"
                            >
                                <el-option v-for="s in SAMPLER_OPTIONS" :key="s" :label="s" :value="s" />
                            </el-select>
                        </div>
                        <div class="ig-field">
                            <span class="ig-label">调度器</span>
                            <el-select
                                v-model="imageGeneration.scheduler"
                                filterable
                                allow-create
                                default-first-option
                                class="ig-num"
                            >
                                <el-option v-for="s in SCHEDULER_OPTIONS" :key="s" :label="s" :value="s" />
                            </el-select>
                        </div>
                        <div class="ig-field ig-field-wide">
                            <span class="ig-label">负面提示词</span>
                            <el-input
                                v-model="imageGeneration.negative_prompt"
                                type="textarea"
                                :rows="3"
                                placeholder="不希望出现的画面元素"
                            />
                        </div>
                    </div>
                    <div class="ig-group-title">生成节奏</div>
                    <div class="ig-grid">
                        <div class="ig-field">
                            <span class="ig-label">冷却间隔（秒）</span>
                            <el-input-number
                                v-model="imageGeneration.interval_seconds"
                                :min="0"
                                :step="30"
                                controls-position="right"
                                class="ig-num"
                            />
                        </div>
                        <div class="ig-field">
                            <span class="ig-label">每会话上限（张）</span>
                            <el-input-number
                                v-model="imageGeneration.max_per_session"
                                :min="1"
                                :step="1"
                                controls-position="right"
                                class="ig-num"
                            />
                        </div>
                        <div class="ig-field">
                            <span class="ig-label">生成超时（秒）</span>
                            <el-input-number
                                v-model="imageGeneration.timeout_seconds"
                                :min="30"
                                :step="30"
                                controls-position="right"
                                class="ig-num"
                            />
                        </div>
                        <div class="ig-field">
                            <span class="ig-label">轮询间隔（秒）</span>
                            <el-input-number
                                v-model="imageGeneration.poll_interval_seconds"
                                :min="0.1"
                                :step="0.5"
                                controls-position="right"
                                class="ig-num"
                            />
                        </div>
                        <div class="ig-field ig-field-wide ig-field-inline">
                            <span class="ig-label">LLM 判定</span>
                            <div class="ig-inline-control">
                                <el-switch v-model="imageGeneration.llm_decision_enabled" />
                                <span class="field-hint">开启后由 LLM 判断本回合是否值得出图；关闭则每回合都生成</span>
                            </div>
                        </div>
                    </div>
                </el-collapse-item>
            </el-collapse>
        </div>
        <div class="config-right page-card" style="align-self: flex-start; flex: 1">
            <div class="page-header">
                <div class="page-title-block">
                    <span class="page-title-icon"><Share theme="filled" size="16" /></span>
                    <div>
                        <h2>图结构</h2>
                        <p class="page-subtitle">LangGraph 双层图拓扑，含插件贡献的节点与子图</p>
                    </div>
                </div>
            </div>
            <GraphView ref="graphRef" inline />
        </div>

        <!-- 系统提示词编辑弹窗 -->
        <el-dialog
            v-model="promptDialogVisible"
            :title="`编辑系统提示词 — ${promptEditingNode?.label || ''}`"
            width="800px"
            destroy-on-close
            class="prompt-dialog"
        >
            <div class="prompt-hint" v-if="promptEditingNode">
                正在编辑节点 <strong>{{ promptEditingNode.id }}</strong> 的系统提示词。
                <span class="prompt-override-badge" v-if="hasPromptOverride(promptEditingNode?.id)">已自定义</span>
                <span class="prompt-default-badge" v-else>使用默认</span>
            </div>
            <div class="ctx-editor-tip">
                <i class="ctx-editor-dot"></i>被蓝色标记的行是上下文注入内容所占的整行，由「上下文注入配置」统一管理，不可在此编辑；其余内容可直接修改。
            </div>
            <div
                ref="promptEditorRef"
                class="prompt-editor"
                contenteditable="true"
                spellcheck="false"
                @input="promptEditorDirty = true"
                @paste="onPromptPaste"
            ></div>
            <template #footer>
                <el-button @click="resetPrompt" :disabled="!hasPromptOverride(promptEditingNode?.id)"
                    >恢复默认</el-button
                >
                <el-button @click="promptDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="confirmPrompt">确定</el-button>
            </template>
        </el-dialog>
    </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import {
    Save,
    Link,
    Download,
    Upload,
    EditOne,
    Check,
    Caution,
    Setting,
    SettingTwo,
    Picture,
    Share,
    Api,
    MindMapping,
    Branch,
    People,
    Camera,
    Eyes,
    RightBranch,
    Memory,
    PeoplePlus,
    Comment,
    Theater,
    FileText,
    Messages,
    Checklist,
    ArrowUp,
    Down,
    Close,
    Magic
} from "@icon-park/vue-next";
import {
    getLlmConfig,
    updateLlmConfig,
    testLlmConfig,
    getNodeParams,
    updateNodeParams,
    getNodeLlmConfig,
    getNodePrompts,
    getNodePromptDefaults,
    updateNodePrompt,
    getFeatures,
    updateFeatures,
    getImageGenerationConfig,
    updateImageGenerationConfig,
    testImageGenerationConfig,
    exportNodeConfig,
    importNodeConfig,
    updateNodeConfig,
    getSystemRules,
    updateSystemRules,
    getNodeContexts,
    updateNodeContexts
} from "../api/config.js";
import { resetSetup } from "../api/setup.js";
import { invalidateSetupCache } from "../router";
import GraphView from "../components/GraphView.vue";

const router = useRouter();
const resettingSetup = ref(false);

// 重新运行首次进入时的配置引导：清除完成标记 → 跳转向导页
async function rerunSetupWizard() {
    resettingSetup.value = true;
    try {
        await resetSetup();
        invalidateSetupCache();
        router.push("/setup");
    } catch (e) {
        ElMessage.error(e.message || "重置失败");
    } finally {
        resettingSetup.value = false;
    }
}

const graphRef = ref(null);
const fileInput = ref(null);
const loading = ref(true);
const saving = ref(false);
const testing = ref(false);
const testResult = ref(null);

const NODE_DEFS = [
    { id: "supervisor_node", label: "调度分析" },
    { id: "director_node", label: "剧情编排" },
    { id: "recall_node", label: "角色召回" },
    { id: "review_env_node", label: "环境审看" },
    { id: "review_character_node", label: "角色审看" },
    { id: "review_departure_node", label: "离场分析" },
    { id: "memory_node", label: "记忆总结" },
    { id: "introduce_character_node", label: "角色引入" },
    { id: "actor_node", label: "角色扮演" },
    { id: "narration_node", label: "旁白生成" },
    { id: "outline_node", label: "剧情总结" },
    { id: "general_narration_node", label: "通用叙述" },
    { id: "player_choice_node", label: "玩家选择" },
    { id: "update_relationship_node", label: "关系更新" },
    { id: "image_gen_node", label: "场景插画" }
];

const NODE_ICON_MAP = {
    supervisor_node: MindMapping,
    director_node: Branch,
    recall_node: People,
    review_env_node: Camera,
    review_character_node: Eyes,
    review_departure_node: RightBranch,
    memory_node: Memory,
    introduce_character_node: PeoplePlus,
    actor_node: Comment,
    narration_node: Theater,
    outline_node: FileText,
    general_narration_node: Messages,
    player_choice_node: Checklist,
    update_relationship_node: Share,
    image_gen_node: Picture
};

// node_llm 覆盖可填字段（与后端 config_loader.NODE_LLM_OVERRIDE_KEYS 对应）
const NODE_LLM_FIELDS = [
    "protocol",
    "api_key",
    "base_url",
    "default_model",
    "timeout_seconds",
    "default_reasoning_effort",
    "max_context_tokens"
];

function nodeIcon(id) {
    return NODE_ICON_MAP[id] || SettingTwo;
}

const nodeParams = reactive({});
for (const nd of NODE_DEFS) {
    nodeParams[nd.id] = {
        temperature: 0,
        max_tokens: 0,
        is_enable_thinking: "disabled",
        reasoning_effort: "",
        max_context_tokens: 0
    };
}

// 逐节点 LLM 覆盖（node_llm）：默认全部继承全局，开启后仅覆盖已填字段
const nodeLlm = reactive({});
const nodeLlmOn = reactive({});
const nodeLlmTestResult = reactive({});
const globalLlm = reactive({});
const nodeLlmTesting = ref("");
for (const nd of NODE_DEFS) {
    nodeLlm[nd.id] = {
        protocol: "",
        api_key: "",
        base_url: "",
        default_model: "",
        timeout_seconds: null,
        default_reasoning_effort: "",
        max_context_tokens: null
    };
    nodeLlmOn[nd.id] = false;
}

const activeCollapse = ref([]);
const savingNodes = ref(false);

// 系统限制（共享）
const systemRules = ref("");
const savingRules = ref(false);

// 系统提示词编辑
const promptDialogVisible = ref(false);
const promptEditingNode = ref(null);
const promptText = ref("");
const promptEditorRef = ref(null);
const promptEditorDirty = ref(false);

// 上下文注入节：=== 标题 ===\n{占位符}（与后端 apply_context_config 同款正则）
const CTX_SECTION_RE = /(=== ?[^=\n]+? ?===\s*\n\{[a-z_]+\})/g;

// 计算上下文节所占的行号集合（0 起；节所在整行锁定，行内其他内容一并锁定）
function computeLockedLines(text) {
    const locked = new Set();
    const lineOf = (pos) => {
        let line = 0;
        for (let i = 0; i < pos; i++) if (text.charCodeAt(i) === 10) line++;
        return line;
    };
    let m;
    CTX_SECTION_RE.lastIndex = 0;
    while ((m = CTX_SECTION_RE.exec(text))) {
        const startLine = lineOf(m.index);
        const endLine = lineOf(m.index + m[0].length - 1);
        for (let l = startLine; l <= endLine; l++) locked.add(l);
    }
    return locked;
}

function renderPromptEditor(text) {
    const el = promptEditorRef.value;
    if (!el) return;
    el.innerHTML = "";
    if (!text) {
        promptEditorDirty.value = false;
        return;
    }
    const locked = computeLockedLines(text);
    const lines = text.split("\n");
    const frag = document.createDocumentFragment();
    // 连续可编辑行合并为文本节点（内部换行保留在文本里）；
    // 连续锁定行合并为一个整行蓝色块（display:block，占满编辑区宽度）
    let editableRun = [];
    const flushEditable = () => {
        if (editableRun.length) {
            frag.appendChild(document.createTextNode(editableRun.join("\n")));
            editableRun = [];
        }
    };
    let i = 0;
    while (i < lines.length) {
        if (locked.has(i)) {
            flushEditable();
            const lockedLines = [];
            while (i < lines.length && locked.has(i)) {
                lockedLines.push(lines[i]);
                i++;
            }
            const span = document.createElement("span");
            span.className = "ctx-locked";
            span.contentEditable = "false";
            span.title = "上下文注入行：由「上下文注入配置」统一管理，此处不可修改";
            span.textContent = lockedLines.join("\n");
            frag.appendChild(span);
        } else {
            editableRun.push(lines[i]);
            i++;
        }
    }
    flushEditable();
    el.appendChild(frag);
    promptEditorDirty.value = false;
}

function collectPromptText() {
    const el = promptEditorRef.value;
    if (!el) return "";
    let out = "";
    const walk = (node, isLast) => {
        if (node.nodeType === Node.TEXT_NODE) {
            out += node.textContent;
        } else if (node.nodeType === Node.ELEMENT_NODE) {
            const locked = node.classList && node.classList.contains("ctx-locked");
            if (locked) {
                // 整行锁定块：行尾换行由块补回（末块除外），保证文本可无损还原
                out += node.textContent;
                if (!isLast && node.parentNode === el) out += "\n";
            } else {
                for (const c of node.childNodes) walk(c, false);
                if (node.tagName === "DIV" || node.tagName === "BR") out += "\n";
            }
        }
    };
    const children = Array.from(el.childNodes);
    children.forEach((c, i) => walk(c, i === children.length - 1));
    return out;
}

function onPromptPaste(e) {
    // 粘贴仅保留纯文本，避免富文本样式污染编辑区
    e.preventDefault();
    const text = (e.clipboardData || window.clipboardData).getData("text/plain");
    document.execCommand("insertText", false, text);
}
const nodeDefaultPrompts = ref({}); // 存储默认提示词，用于判断是否有自定义
const nodeCustomPrompts = ref({}); // 存储当前配置的提示词
const promptSaved = ref({}); // 上次保存时的提示词快照
const promptDirty = ref(new Set()); // 有未保存提示词改动的节点 ID

const form = reactive({
    protocol: "openai",
    api_key: "",
    base_url: "",
    default_model: "",
    default_temperature: 0.9,
    default_max_tokens: 8192,
    is_enable_thinking: "enabled",
    default_reasoning_effort: "high",
    max_context_tokens: 0,
    features: {
        player_choice_enabled: true,
        memory_summarize_interval: 10
    }
});

// 场景插画（image_gen_node / ComfyUI，独立服务）
const imageGeneration = reactive({
    enabled: false,
    comfyui_base_url: "http://127.0.0.1:8188",
    checkpoint: "animagine-xl-4.0.safetensors",
    width: 896,
    height: 1152,
    steps: 30,
    cfg: 6.0,
    sampler_name: "dpmpp_2m",
    scheduler: "karras",
    negative_prompt: "",
    interval_seconds: 180,
    max_per_session: 30,
    llm_decision_enabled: true,
    timeout_seconds: 300,
    poll_interval_seconds: 1.0
});
const testingComfyui = ref(false);
const savingImageGen = ref(false);
const comfyuiTestResult = ref(null);
const checkpointOptions = ref([]);

const SAMPLER_OPTIONS = [
    "euler",
    "euler_ancestral",
    "heun",
    "dpm_2",
    "dpm_2_ancestral",
    "lms",
    "dpmpp_2s_ancestral",
    "dpmpp_sde",
    "dpmpp_2m",
    "dpmpp_2m_sde",
    "dpmpp_3m_sde",
    "ddpm",
    "lcm",
    "ddim",
    "uni_pc",
    "res_multistep"
];
const SCHEDULER_OPTIONS = [
    "normal",
    "karras",
    "exponential",
    "sgm_uniform",
    "simple",
    "ddm_uniform",
    "beta",
    "linear_quadratic",
    "kl_optimal"
];

const URL_PATTERN = /^https?:\/\/.+/;

// Base URL 占位符随协议切换；切换协议时若地址仍为另一协议的默认值则一并替换
const baseUrlPlaceholder = computed(() =>
    form.protocol === "anthropic" ? "https://api.anthropic.com" : "https://api.openai.com/v1"
);
const PROTOCOL_DEFAULT_URLS = {
    openai: "https://api.openai.com/v1",
    anthropic: "https://api.anthropic.com"
};
function onGlobalProtocolChange() {
    const defaults = Object.values(PROTOCOL_DEFAULT_URLS);
    if (!form.base_url || defaults.includes(form.base_url)) {
        form.base_url = PROTOCOL_DEFAULT_URLS[form.protocol];
    }
}

onMounted(async () => {
    try {
        const cfg = await getLlmConfig();
        if (cfg) Object.assign(form, cfg);
    } catch {
        /* use defaults */
    }
    try {
        const np = await getNodeParams();
        if (np) {
            for (const nd of NODE_DEFS) {
                Object.assign(nodeParams[nd.id], np[nd.id] || {});
            }
        }
    } catch {
        /* keep defaults */
    } finally {
        loading.value = false;
    }
    loadFeatures();
    loadImageGeneration();
    loadNodePrompts();
    loadSystemRules();
    loadNodeContexts();
    loadNodeLlm();
});

// ── 逐节点 LLM 覆盖（node_llm） ──

async function loadNodeLlm() {
    try {
        const data = await getNodeLlmConfig();
        const overrides = (data && data.node_llm) || {};
        Object.assign(globalLlm, (data && data.global) || {});
        for (const nd of NODE_DEFS) {
            const o = overrides[nd.id] || {};
            Object.assign(nodeLlm[nd.id], o);
            nodeLlmOn[nd.id] = Object.keys(o).length > 0;
        }
    } catch {
        /* keep defaults */
    }
}

function nodeLlmPlaceholder(key) {
    if (key === "api_key") return form.api_key ? "继承全局（已设置）" : "继承全局（未设置）";
    if (key === "timeout_seconds") return `继承全局：${globalLlm.timeout_seconds || 600}`;
    const val = form[key];
    return val ? `继承全局：${val}` : "继承全局";
}

function clearNodeLlm(id) {
    Object.assign(nodeLlm[id], {
        protocol: "",
        api_key: "",
        base_url: "",
        default_model: "",
        timeout_seconds: null,
        default_reasoning_effort: "",
        max_context_tokens: null
    });
    nodeLlmOn[id] = false;
    delete nodeLlmTestResult[id];
}

async function testNodeLlm(id) {
    const o = nodeLlm[id];
    if (!validURL(o.base_url)) return;
    nodeLlmTesting.value = id;
    try {
        const res = await testLlmConfig({
            protocol: o.protocol || form.protocol,
            api_key: o.api_key || form.api_key,
            base_url: o.base_url || form.base_url,
            default_model: o.default_model || form.default_model
        });
        nodeLlmTestResult[id] = res;
    } catch (e) {
        nodeLlmTestResult[id] = { success: false, error: e.message || "请求失败", elapsed_ms: 0 };
    } finally {
        nodeLlmTesting.value = "";
    }
}

function buildNodeLlmPayload() {
    const payload = {};
    for (const nd of NODE_DEFS) {
        if (!nodeLlmOn[nd.id]) continue;
        const entry = {};
        for (const key of NODE_LLM_FIELDS) {
            const val = nodeLlm[nd.id][key];
            if (val === "" || val === null || val === undefined) continue; // 留空继承全局
            entry[key] = val;
        }
        if (Object.keys(entry).length) payload[nd.id] = entry;
    }
    return payload;
}

async function loadSystemRules() {
    try {
        const data = await getSystemRules();
        if (data && data.system_rules != null) {
            systemRules.value = data.system_rules;
        }
    } catch {
        /* keep empty */
    }
}

async function saveSystemRules() {
    savingRules.value = true;
    try {
        await updateSystemRules({ system_rules: systemRules.value });
        ElMessage.success("系统限制已保存，下次对话生效");
    } catch (e) {
        ElMessage.error(e.message || "保存失败");
    } finally {
        savingRules.value = false;
    }
}

async function resetSystemRules() {
    try {
        await updateSystemRules({ system_rules: "" });
        await loadSystemRules();
        ElMessage.success("已清空共享限制");
    } catch (e) {
        ElMessage.error(e.message || "恢复失败");
    }
}

// ── 上下文注入配置（每节点） ──
const CTX_NODE_OPTIONS = [
    ...NODE_DEFS,
    { id: "player_choice_process", label: "玩家选择-处理" }
];
const ctxNode = ref("supervisor_node");
const ctxNodeContexts = ref({}); // { node: [{id,title?}] }
const ctxBlocksCatalog = ref([]); // [{id,title,desc}]
const ctxAddId = ref("");
const savingCtx = ref(false);
const ctxDirty = ref(false);

const ctxCurrent = computed(() => {
    const list = ctxNodeContexts.value[ctxNode.value] || [];
    return list.map((b) => (typeof b === "string" ? { id: b } : { ...b }));
});
const ctxAddable = computed(() => {
    const have = new Set(ctxCurrent.value.map((b) => b.id));
    return ctxBlocksCatalog.value.filter((b) => !have.has(b.id));
});

function ctxTitle(b) {
    if (b.title) return b.title;
    const cat = ctxBlocksCatalog.value.find((c) => c.id === b.id);
    return cat ? cat.title : b.id;
}

async function loadNodeContexts() {
    try {
        const res = await getNodeContexts();
        if (res) {
            ctxNodeContexts.value = res.node_contexts || {};
            ctxBlocksCatalog.value = res.blocks || [];
            if (!ctxNodeContexts.value[ctxNode.value]) ctxNode.value = "supervisor_node";
        }
    } catch {
        /* ignore */
    }
}

function mutateCtx(fn) {
    const list = ctxCurrent.value.map((b) => ({ ...b }));
    fn(list);
    ctxNodeContexts.value = { ...ctxNodeContexts.value, [ctxNode.value]: list };
    ctxDirty.value = true;
}

function moveCtx(i, dir) {
    mutateCtx((list) => {
        const j = i + dir;
        if (j < 0 || j >= list.length) return;
        [list[i], list[j]] = [list[j], list[i]];
    });
}

function removeCtx(i) {
    mutateCtx((list) => list.splice(i, 1));
}

function addCtx() {
    if (!ctxAddId.value) return;
    mutateCtx((list) => list.push({ id: ctxAddId.value }));
    ctxAddId.value = "";
}

async function saveNodeContexts() {
    savingCtx.value = true;
    try {
        await updateNodeContexts({ node_contexts: ctxNodeContexts.value });
        ctxDirty.value = false;
        ElMessage.success("上下文注入已保存，下次对话生效");
    } catch (e) {
        ElMessage.error(e.message || "保存失败");
    } finally {
        savingCtx.value = false;
    }
}

async function resetCtxNode() {
    const next = { ...ctxNodeContexts.value };
    delete next[ctxNode.value];
    try {
        await updateNodeContexts({ node_contexts: next });
        ctxNodeContexts.value = next;
        ctxDirty.value = false;
        ElMessage.success("已恢复该节点默认上下文注入");
    } catch (e) {
        ElMessage.error(e.message || "恢复失败");
    }
}

function validURL(url) {
    if (!url) return true;
    if (!URL_PATTERN.test(url)) {
        ElMessage.warning("Base URL 格式不正确，应以 http:// 或 https:// 开头");
        return false;
    }
    return true;
}

async function save() {
    if (!validURL(form.base_url)) return;
    saving.value = true;
    try {
        await updateLlmConfig({
            protocol: form.protocol,
            api_key: form.api_key,
            base_url: form.base_url,
            default_model: form.default_model,
            default_temperature: form.default_temperature,
            default_max_tokens: form.default_max_tokens,
            is_enable_thinking: form.is_enable_thinking,
            default_reasoning_effort: form.default_reasoning_effort,
            max_context_tokens: form.max_context_tokens,
        });
        ElMessage.success("配置已保存，将在下次对话时生效");
    } catch (e) {
        ElMessage.error(e.message || "保存失败");
    } finally {
        saving.value = false;
    }
}

async function test() {
    if (!validURL(form.base_url)) return;
    testing.value = true;
    testResult.value = null;
    try {
        const res = await testLlmConfig({ ...form });
        testResult.value = res;
    } catch (e) {
        testResult.value = { success: false, error: e.message || "请求失败", elapsed_ms: 0 };
    } finally {
        testing.value = false;
    }
}

async function loadFeatures() {
    try {
        const feats = await getFeatures();
        if (feats) Object.assign(form.features, feats);
    } catch {
        /* keep defaults */
    }
}

async function saveFeatures() {
    try {
        await updateFeatures({ ...form.features });
        graphRef.value?.loadTopology?.();
        ElMessage.success("功能配置已保存");
    } catch (e) {
        ElMessage.error(e.message || "保存失败");
    }
}

async function loadImageGeneration() {
    try {
        const ig = await getImageGenerationConfig();
        if (ig) Object.assign(imageGeneration, ig);
    } catch {
        /* keep defaults */
    }
}

async function fetchCheckpoints({ silent = false } = {}) {
    const url = (imageGeneration.comfyui_base_url || "").trim();
    if (!url) return;
    if (!URL_PATTERN.test(url)) {
        if (!silent) ElMessage.warning("服务地址格式不正确，应以 http:// 或 https:// 开头");
        return;
    }
    testingComfyui.value = true;
    try {
        const res = await testImageGenerationConfig({ comfyui_base_url: url });
        if (res?.success) checkpointOptions.value = res.checkpoints || [];
        if (!silent) comfyuiTestResult.value = res;
    } catch (e) {
        if (!silent) {
            comfyuiTestResult.value = { success: false, error: e.message || "请求失败", elapsed_ms: 0 };
        }
    } finally {
        testingComfyui.value = false;
    }
}

function testComfyui() {
    return fetchCheckpoints({ silent: false });
}

function onCollapseChange(names) {
    // 首次展开插画折叠区时静默预取 checkpoint 列表，失败不打扰用户
    if (
        names.includes("image_gen") &&
        checkpointOptions.value.length === 0 &&
        imageGeneration.comfyui_base_url
    ) {
        fetchCheckpoints({ silent: true });
    }
}

async function saveImageGenConfig() {
    if (!URL_PATTERN.test(imageGeneration.comfyui_base_url || "")) {
        ElMessage.warning("服务地址格式不正确，应以 http:// 或 https:// 开头");
        return;
    }
    savingImageGen.value = true;
    try {
        await updateImageGenerationConfig({ ...imageGeneration });
        graphRef.value?.loadTopology?.();
        ElMessage.success("场景插画配置已保存，下次对话生效");
    } catch (e) {
        ElMessage.error(e.message || "保存失败");
    } finally {
        savingImageGen.value = false;
    }
}

async function saveNodeParams() {
    const nodeLlmPayload = buildNodeLlmPayload();
    for (const [id, entry] of Object.entries(nodeLlmPayload)) {
        if (!validURL(entry.base_url)) {
            ElMessage.warning(`${id} 的 Base URL 格式不正确，应以 http:// 或 https:// 开头`);
            return;
        }
    }
    savingNodes.value = true;
    try {
        const prompts = {};
        for (const nd of NODE_DEFS) {
            prompts[nd.id] = nodeCustomPrompts.value[nd.id] || "";
        }
        await updateNodeConfig({
            node_params: { ...nodeParams },
            node_prompts: prompts,
            node_llm: nodeLlmPayload
        });
        promptSaved.value = { ...nodeCustomPrompts.value };
        promptDirty.value.clear();
        ElMessage.success("节点参数已保存");
    } catch (e) {
        ElMessage.error(e.message || "保存失败");
    } finally {
        savingNodes.value = false;
    }
}

// ── 系统提示词编辑 ──

async function loadNodePrompts() {
    try {
        if (Object.keys(nodeDefaultPrompts.value).length === 0) {
            const defaults = await getNodePromptDefaults();
            if (defaults) {
                nodeDefaultPrompts.value = { ...defaults };
            }
        }
        const prompts = await getNodePrompts();
        if (prompts) {
            nodeCustomPrompts.value = { ...prompts };
            promptSaved.value = { ...prompts };
            promptDirty.value.clear();
        }
    } catch {
        /* ignore */
    }
}

function hasPromptOverride(nodeId) {
    if (!nodeId) return false;
    // 判断：如果自定义值与默认值不同，说明有 override
    const custom = nodeCustomPrompts.value[nodeId];
    const def = nodeDefaultPrompts.value[nodeId];
    return custom !== undefined && custom !== def;
}

function editPrompt(nd) {
    promptEditingNode.value = nd;
    promptText.value = nodeCustomPrompts.value[nd.id] || "";
    promptDialogVisible.value = true;
    nextTick(() => renderPromptEditor(promptText.value));
}

function resetPrompt() {
    const nd = promptEditingNode.value;
    if (!nd) return;
    promptText.value = nodeDefaultPrompts.value[nd.id] || "";
    renderPromptEditor(promptText.value);
}

function confirmPrompt() {
    const nd = promptEditingNode.value;
    if (!nd) return;
    const text = collectPromptText();
    nodeCustomPrompts.value[nd.id] = text;
    if (text !== promptSaved.value[nd.id]) {
        promptDirty.value.add(nd.id);
    } else {
        promptDirty.value.delete(nd.id);
    }
    promptDialogVisible.value = false;
    ElMessage.success("提示词已暂存，请点击底部 「保存节点参数」 使其生效");
}

function triggerImportConfig() {
    fileInput.value?.click();
}

async function onFileSelected(e) {
    const file = e.target.files[0];
    if (!file) return;
    try {
        const text = await file.text();
        const data = JSON.parse(text);
        const res = await importNodeConfig(data);
        if (res && res.msg === "配置文件内容为空，未做修改") {
            ElMessage.warning(res.msg);
        } else {
            const np = await getNodeParams();
            if (np) {
                for (const nd of NODE_DEFS) {
                    Object.assign(nodeParams[nd.id], np[nd.id] || {});
                }
            }
            const prompts = await getNodePrompts();
            if (prompts) {
                nodeCustomPrompts.value = { ...prompts };
                promptSaved.value = { ...prompts };
                promptDirty.value.clear();
            }
            ElMessage.success("节点配置已导入");
        }
    } catch (err) {
        ElMessage.error(err.message || "导入失败，请检查文件格式");
    } finally {
        fileInput.value.value = "";
    }
}

async function handleExportConfig() {
    try {
        const blob = await exportNodeConfig();
        const text = await blob.text();
        const data = JSON.parse(text);
        if (!data.node_params || Object.keys(data.node_params).length === 0) {
            ElMessage.warning("节点参数从未修改过，导出内容为空");
            return;
        }
        const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
        const a = document.createElement("a");
        a.href = url;
        a.download = "node_config.json";
        a.click();
        URL.revokeObjectURL(url);
        ElMessage.success("导出成功");
    } catch (err) {
        ElMessage.error(err.message || "导出失败");
    }
}
</script>

<style scoped>
.config-layout {
    display: flex;
    gap: 16px;
    align-items: flex-start;
}
.config-left {
    width: 640px;
    flex-shrink: 0;
}
.config-right {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    position: sticky;
    top: 20px;
}
.config-right :deep(.graph-view-inline) {
    min-height: 500px;
}
.config-form {
    max-width: none;
}
.config-btn {
    min-width: 100px;
    display: inline-flex;
    align-items: center;
}

/* ── 上置标签 + 两列网格（配置页统一紧凑布局，对齐 ig-grid 风格） ── */
.form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0 16px;
}
.grid-span-2 {
    grid-column: 1 / -1;
}
.form-grid :deep(.el-form-item) {
    margin-bottom: 14px;
}
.form-grid :deep(.el-form-item__label) {
    padding-bottom: 4px;
    line-height: 1.4;
}
.form-grid :deep(.el-form-item__content) {
    flex-wrap: wrap;
    row-gap: 3px;
}
.form-grid :deep(.el-select),
.form-grid :deep(.el-input-number),
.form-grid :deep(.el-input) {
    width: 100%;
}
.form-grid .field-hint {
    width: 100%;
    line-height: 1.5;
}
.inline-control {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
}
.inline-control :deep(.el-slider) {
    flex: 1;
    min-width: 0;
}
.form-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 4px;
}

/* ── 卡片内分区区块（LLM 配置 / 功能开关） ── */
.cfg-block {
    background: #f8fafd;
    border: 1px solid var(--border-light, #eef1f5);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 14px;
}
.cfg-block :deep(.el-form-item) {
    margin-bottom: 12px;
}
.cfg-block :deep(.el-form-item:last-of-type) {
    margin-bottom: 0;
}

/* ── 卡片内小节标题 ── */
.section-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 8px;
}
.section-title {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary, #1e2a3a);
}
.section-icon {
    color: var(--brand-500, #5d9eff);
}
.section-note {
    font-size: 12px;
    color: var(--text-muted, #909399);
}

/* ── 折叠区通用 ── */
.collapse-hint {
    font-size: 13px;
    color: var(--text-muted, #909399);
    margin: 0 0 12px;
    line-height: 1.6;
}
.collapse-actions {
    margin-top: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ── 测试结果面板 ── */
.test-result {
    margin-top: 12px;
    padding: 12px 14px;
    border-radius: 10px;
    font-size: 13px;
    line-height: 1.5;
}
.test-success {
    background: #eef8f1;
    border: 1px solid #d3efe0;
}
.test-fail {
    background: #fef0f0;
    border: 1px solid #fde2e2;
}
.test-result-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    font-weight: 600;
}
.test-icon-success {
    color: #18a058;
}
.test-icon-fail {
    color: #f56c6c;
}
.test-status {
    font-size: 13px;
}
.test-success .test-status {
    color: #18a058;
}
.test-fail .test-status {
    color: #f56c6c;
}
.test-elapsed {
    font-size: 12px;
    color: var(--text-muted, #909399);
    font-weight: 400;
}
.test-response {
    color: var(--text-primary, #1e2a3a);
}
.test-error {
    color: #f56c6c;
}

/* ── 配置折叠区（圆角卡片条式折叠头） ── */
.cfg-collapse {
    border: none;
    background: transparent;
    margin-top: 4px;
}
.cfg-collapse :deep(.el-collapse-item__header) {
    height: 46px;
    border: none;
    background: var(--el-fill-color, #f5f8fc);
    border-radius: 10px;
    padding: 0 14px;
    margin-bottom: 8px;
    transition: background-color 0.15s ease, color 0.15s ease;
}
.cfg-collapse :deep(.el-collapse-item__header:hover) {
    background: var(--brand-50, #f0f6ff);
}
.cfg-collapse :deep(.el-collapse-item__header.is-active) {
    background: var(--brand-50, #f0f6ff);
    color: var(--brand-600, #2b6dd9);
}
.cfg-collapse :deep(.el-collapse-item__header .el-collapse-item__arrow) {
    color: var(--text-muted, #909399);
}
.cfg-collapse :deep(.el-collapse-item:last-of-type .el-collapse-item__header) {
    margin-bottom: 0;
}
.cfg-collapse :deep(.el-collapse-item__wrap) {
    border-bottom: none;
    background: transparent;
}
.cfg-collapse :deep(.el-collapse-item__content) {
    padding: 4px 6px 20px;
    color: var(--text-primary, #1e2a3a);
}
.cfg-collapse-title {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary, #1e2a3a);
}
.cfg-collapse-icon {
    color: var(--brand-500, #5d9eff);
}
.cfg-collapse-sub {
    font-size: 12px;
    font-weight: 400;
    color: var(--text-muted, #909399);
    margin-left: 4px;
}

/* ── 节点参数卡片 ── */
.node-card {
    border: 1px solid var(--border-light, #eef0f3);
    border-radius: 12px;
    padding: 12px 16px;
    margin-bottom: 12px;
    background: var(--el-fill-color, #f7f8fa);
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.node-card:hover {
    border-color: var(--brand-200, #c8dcff);
    box-shadow: var(--shadow-1);
}
.node-card-title {
    display: flex;
    align-items: center;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary, #1e2a3a);
    margin-bottom: 10px;
}
.node-card-icon {
    margin-right: 6px;
    color: var(--brand-500, #5d9eff);
    flex-shrink: 0;
}
.node-card-id {
    font-size: 11px;
    font-weight: 500;
    color: #8a94a6;
    background: #eef1f5;
    border-radius: 20px;
    padding: 1px 8px;
    margin-left: 8px;
    font-family: Consolas, Monaco, monospace;
}
.node-val {
    margin-left: 8px;
    font-size: 13px;
    color: var(--text-secondary, #606266);
    min-width: 30px;
    display: inline-block;
}
.node-val-disabled {
    color: #c0c4cc;
}
.node-card-actions {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border-light, #e8eaed);
}
.node-card-actions .el-button {
    display: inline-flex;
    align-items: center;
    gap: 4px;
}

/* ── 节点级 LLM 覆盖 ── */
.node-llm {
    margin-top: 10px;
    border: 1px solid #eef2f8;
    background: #fbfcfe;
    border-radius: 10px;
    padding: 10px 12px;
}
.node-llm-head {
    display: flex;
    align-items: center;
    gap: 8px;
}
.node-llm-title {
    display: inline-flex;
    align-items: center;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary, #1e2a3a);
}
.node-llm-icon {
    margin-right: 4px;
    color: var(--brand-500, #5d9eff);
}
.node-llm-note {
    font-size: 12px;
    color: var(--text-muted, #909399);
}
.node-llm-form {
    margin-top: 8px;
}
.node-llm-form :deep(.el-input-number) {
    width: 100%;
}
.node-llm-actions {
    display: flex;
    align-items: center;
    gap: 4px;
}
.node-llm-result {
    margin-top: 6px;
    padding: 6px 10px;
    border-radius: 8px;
    font-size: 12px;
    line-height: 1.5;
    word-break: break-all;
}
.node-llm-ok {
    background: #eef8f1;
    border: 1px solid #d3efe0;
    color: #18a058;
}
.node-llm-fail {
    background: #fef0f0;
    border: 1px solid #fde2e2;
    color: #f56c6c;
}

/* ── 场景插画配置 ── */
.ig-connection {
    background: var(--brand-50, #f0f6ff);
    border: 1px solid var(--brand-100, #e2edff);
    border-radius: 10px;
    padding: 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 12px;
}
.ig-conn-row {
    display: flex;
    align-items: center;
    gap: 10px;
}
.ig-conn-label {
    font-size: 13px;
    color: var(--text-secondary, #5b6779);
    width: 64px;
    flex-shrink: 0;
}
.ig-conn-input {
    flex: 1;
    min-width: 0;
}
.ig-conn-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
}
.field-hint {
    font-size: 12px;
    color: var(--text-muted, #909399);
}
.ig-group-title {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted, #909399);
    letter-spacing: 0.05em;
    margin: 16px 0 10px;
}
.ig-group-title::after {
    content: "";
    flex: 1;
    height: 1px;
    background: var(--border-light, #e9edf3);
}
.ig-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px 16px;
}
.ig-field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
}
.ig-field-wide {
    grid-column: 1 / -1;
}
.ig-field-inline {
    gap: 0;
}
.ig-inline-control {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-top: 4px;
}
.ig-label {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-secondary, #5b6779);
}
.ig-num {
    width: 100%;
}
.ig-mt {
    margin-top: 12px;
}

.prompt-dialog :deep(.el-dialog__body) {
    padding-top: 10px;
}
.prompt-hint {
    font-size: 13px;
    color: var(--text-muted, #909399);
    margin-bottom: 12px;
}
.prompt-override-badge {
    display: inline-block;
    margin-left: 8px;
    padding: 1px 8px;
    font-size: 12px;
    background: var(--brand-50, #eef4ff);
    color: var(--brand-600, #2b6dd9);
    border-radius: 4px;
}
.prompt-default-badge {
    display: inline-block;
    margin-left: 8px;
    padding: 1px 8px;
    font-size: 12px;
    background: #f5f7fa;
    color: var(--text-muted, #909399);
    border-radius: 4px;
}
/* 上下文注入节锁定提示条 */
.ctx-editor-tip {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    font-size: 12px;
    color: var(--text-secondary, #606266);
    background: #f7f9fc;
    border: 1px solid #eef1f5;
    border-radius: 8px;
    padding: 6px 10px;
    margin-bottom: 10px;
    line-height: 1.6;
}
.ctx-editor-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--brand-500, #5d9eff);
    flex-shrink: 0;
    margin-top: 5px;
}
/* 可编辑提示词容器（contenteditable） */
.prompt-editor {
    font-family: "Consolas", "Monaco", "Courier New", monospace;
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
    border: 1px solid #dcdfe6;
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 320px;
    max-height: 480px;
    overflow-y: auto;
    outline: none;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.prompt-editor:focus {
    border-color: var(--brand-500, #5d9eff);
    box-shadow: 0 0 0 3px rgba(93, 158, 255, 0.15);
}
.prompt-editor:empty::before {
    content: "输入系统提示词...";
    color: #c0c4cc;
}
/* 上下文注入行：整行蓝色标记 + 锁定不可编辑
   （span 由 JS 动态创建、无 scoped 属性，须用 :deep() 命中） */
.prompt-editor :deep(.ctx-locked) {
    display: block;
    white-space: pre-wrap;
    word-break: break-word;
    background: var(--brand-50, #f0f6ff);
    border-left: 3px solid var(--brand-400, #7cb0ff);
    color: var(--brand-700, #3a72d4);
    padding: 1px 8px;
    cursor: not-allowed;
    user-select: all;
    min-height: 1.6em;
}
.prompt-editor :deep(.ctx-locked:hover) {
    background: var(--brand-100, #e2edff);
}
.prompt-unsaved-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #e6a23c;
    margin-left: 4px;
    vertical-align: middle;
}
.unsaved-hint {
    color: #e6a23c;
    font-size: 12px;
}
/* 上下文注入配置 */
.ctx-node-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
}
.ctx-node-label {
    font-size: 13px;
    color: var(--text-secondary, #606266);
}
.ctx-blocks {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 12px;
}
.ctx-block-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    background: #f7f9fc;
    border: 1px solid #eef1f5;
    border-radius: 8px;
    font-size: 13px;
}
.ctx-block-order {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--brand-500, #5d9eff);
    color: #fff;
    font-size: 12px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}
.ctx-block-title {
    color: var(--text-primary, #1e2a3a);
    font-weight: 500;
}
.ctx-block-id {
    color: var(--text-muted, #909399);
    font-size: 12px;
    margin-right: auto;
    font-family: Consolas, Monaco, monospace;
}
.ctx-empty {
    color: var(--text-muted, #909399);
    font-size: 13px;
    padding: 8px 10px;
    background: #fafbfd;
    border: 1px dashed #e0e4ea;
    border-radius: 8px;
}
.ctx-add-row {
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ── 窄屏：左右单列，图结构跟随文档流 ── */
@media (max-width: 1080px) {
    .config-layout {
        flex-direction: column;
    }
    .config-left {
        width: 100%;
        flex-shrink: 1;
    }
    .config-right {
        position: static;
        width: 100%;
    }
}
</style>
