/**
 * Handles comment generation functionality in the UI
 */
export class CommentController {
  constructor(viewManager, modalManager) {
    this.viewManager = viewManager;
    this.modalManager = modalManager;

    // Element references
    this.generateCommentButton = document.getElementById("generate-comment");
    this.commentsList = document.getElementById("comments-list");

    // State
    this.comments = [];

    // Setup event listeners
    this.setupEventListeners();
  }

  /**
   * Set up event listeners for comment-related elements
   */
  setupEventListeners() {
    this.generateCommentButton.addEventListener(
      "click",
      this.showGenerateCommentModal.bind(this)
    );

    // Listen for user login event to load comments
    document.addEventListener("user:loggedin", () => {
      this.loadComments();
    });
  }

  /**
   * Show modal for generating a new comment
   */
  async showGenerateCommentModal() {
    // Create modal content with form
    const formContainer = document.createElement("div");
    formContainer.innerHTML = `
      <form id="generate-comment-form">
        <div class="form-group">
          <label for="post-text">LinkedIn Post Text</label>
          <textarea id="post-text" name="postText" rows="6" required placeholder="Paste the text of the LinkedIn post here"></textarea>
        </div>
        <div class="form-group">
          <label for="post-url">LinkedIn Post URL (Optional)</label>
          <input type="url" id="post-url" name="postUrl" placeholder="https://www.linkedin.com/feed/update/...">
        </div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary">Generate Comment</button>
        </div>
      </form>
    `;

    // Show the modal
    this.modalManager.showModal("Generate LinkedIn Comment", formContainer);

    // Handle form submission
    const form = formContainer.querySelector("#generate-comment-form");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const postText = form.postText.value.trim();
      const postUrl = form.postUrl.value.trim();

      if (!postText) {
        this.modalManager.alert(
          "Please enter the LinkedIn post text.",
          "Validation Error"
        );
        return;
      }

      try {
        // Show loading state
        const submitButton = form.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.textContent = "Generating...";

        // Call API to generate comment
        const commentRequest = {
          post_text: postText,
          source_linkedin_url: postUrl || null,
        };

        const result = await window.api.comments.generate(commentRequest);

        if (result) {
          // Close the modal
          this.modalManager.closeModal();

          // Show the generated comment
          this.displayGeneratedComment(result);

          // Add to comments list
          this.addComment(result);
        }
      } catch (error) {
        console.error("Comment generation error:", error);
        this.modalManager.alert(
          error.message || "Failed to generate comment. Please try again.",
          "Generation Error"
        );

        // Reset button
        const submitButton = form.querySelector('button[type="submit"]');
        submitButton.disabled = false;
        submitButton.textContent = "Generate Comment";
      }
    });
  }

  /**
   * Display a generated comment in a modal
   * @param {Object} commentData - Comment data
   */
  displayGeneratedComment(commentData) {
    const commentContent = document.createElement("div");
    commentContent.classList.add("generated-comment");

    commentContent.innerHTML = `
      <p class="comment-text">${commentData.comment}</p>
      <div class="comment-meta">
        <div class="comment-status">
          <span class="status-label">Status:</span>
          <span class="status-value ${
            commentData.verified ? "verified" : "unverified"
          }">
            ${commentData.verified ? "Verified" : "Unverified"}
          </span>
        </div>
        ${
          commentData.failure_reason
            ? `<div class="failure-reason">Issue: ${commentData.failure_reason}</div>`
            : ""
        }
      </div>
      <div class="comment-actions">
        <button id="copy-comment" class="btn btn-secondary">Copy to Clipboard</button>
        <button id="close-comment" class="btn">Close</button>
      </div>
    `;

    // Show the comment in a modal
    this.modalManager.showModal("Generated Comment", commentContent);

    // Handle copy button
    const copyButton = commentContent.querySelector("#copy-comment");
    copyButton.addEventListener("click", () => {
      navigator.clipboard
        .writeText(commentData.comment)
        .then(() => {
          copyButton.textContent = "Copied!";
          setTimeout(() => {
            copyButton.textContent = "Copy to Clipboard";
          }, 2000);
        })
        .catch((err) => {
          console.error("Failed to copy comment:", err);
          this.modalManager.alert(
            "Failed to copy comment to clipboard.",
            "Copy Error"
          );
        });
    });

    // Handle close button
    const closeButton = commentContent.querySelector("#close-comment");
    closeButton.addEventListener("click", () => {
      this.modalManager.closeModal();
    });
  }

  /**
   * Add a comment to the comments list
   * @param {Object} commentData - Comment data
   */
  addComment(commentData) {
    // Add to local state
    this.comments.unshift(commentData);

    // Update UI
    this.renderCommentsList();
  }

  /**
   * Load comments from history
   */
  async loadComments() {
    try {
      // In a real implementation, you would fetch comments from storage or API
      // For now, we'll just clear the list
      this.comments = [];
      this.renderCommentsList();
    } catch (error) {
      console.error("Error loading comments:", error);
      this.renderCommentsList();
    }
  }

  /**
   * Render the comments list
   */
  renderCommentsList() {
    // Clear current content
    this.commentsList.innerHTML = "";

    if (this.comments.length === 0) {
      this.commentsList.innerHTML =
        '<p class="empty-state">No comments generated yet</p>';
      return;
    }

    // Create comment items
    for (const comment of this.comments) {
      const commentItem = document.createElement("div");
      commentItem.classList.add("comment-item");

      // Truncate long comments for display
      const truncatedComment =
        comment.comment.length > 100
          ? comment.comment.substring(0, 100) + "..."
          : comment.comment;

      commentItem.innerHTML = `
        <div class="comment-content">
          <p class="comment-text">${truncatedComment}</p>
          <div class="comment-meta">
            <div class="comment-status">
              <span class="status-value ${
                comment.verified ? "verified" : "unverified"
              }">
                ${comment.verified ? "Verified" : "Unverified"}
              </span>
            </div>
            ${
              comment.comment_date
                ? `<div class="comment-date">${new Date(
                    comment.comment_date
                  ).toLocaleDateString()}</div>`
                : ""
            }
          </div>
        </div>
        <div class="comment-actions">
          <button class="btn btn-small view-comment">View</button>
        </div>
      `;

      // Add event listener to view button
      const viewButton = commentItem.querySelector(".view-comment");
      viewButton.addEventListener("click", () => {
        this.displayGeneratedComment(comment);
      });

      this.commentsList.appendChild(commentItem);
    }
  }
}
