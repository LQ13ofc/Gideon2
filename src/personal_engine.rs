//! WP-10a: the Core side of `personal::SkillEngine`. Kept in its own file so the personal-data areas
//! reach the skills engine only through the public snapshot and the engine's own entry points:
//! `skills_view()` (enabled version with dependencies and permissions satisfied) and `skill_run()` (every
//! grant, dependency and busy check of the engine).

use crate::{core::Core, personal::SkillEngine, skills::State};
use serde_json::Value;

impl SkillEngine for Core {
    fn enabled_version(&self, skill_id: &str) -> Option<String> {
        self.skills_view()?
            .items
            .into_iter()
            .find(|item| {
                item.id == skill_id
                    && item.active
                    && item.state == State::Enabled
                    && item.deps_ok
                    && item.permissions_ok
            })
            .map(|item| item.version)
    }

    fn run_skill(&mut self, skill_id: &str, inputs: Value) -> &'static str {
        self.skill_run(skill_id, inputs)
    }
}
