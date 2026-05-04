const tasks = [
  { id: 1, title: "整理需求文档", done: false },
  { id: 2, title: "补充接口说明", done: false },
  { id: 3, title: "同步测试结果", done: true },
];

const taskList = document.querySelector("#taskList");

function renderTasks() {
  taskList.innerHTML = "";

  tasks.forEach((task) => {
    const item = document.createElement("li");
    item.className = task.done ? "task-item is-done" : "task-item";
    item.textContent = task.title;
    taskList.appendChild(item);
  });
}

renderTasks();
