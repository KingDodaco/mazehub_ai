# MazeHub Portable Launcher

This setup keeps the full development project on your machine and publishes a simple pipeline bundle that can be copied to another location.

## Recommended workflow
1. Keep your full project in your development environment.
2. Run the publish script whenever you want to publish changes.
3. Copy the contents of the publish/pipeline folder to the target project structure.
4. Launch the app from the copied mazehub folder using launch_mazehub.bat.

## Files
- publish_pipeline.py: syncs the mirrored pipeline into the working tree and publishes a clean publish/pipeline bundle.
- publish_pipeline.bat: Windows wrapper for the publish script.
- launch_mazehub.bat: launches the app from the published mazehub folder.

## Windows usage
- Run publish_pipeline.bat from your dev environment.
- Copy the generated publish/pipeline folder to the target location.
