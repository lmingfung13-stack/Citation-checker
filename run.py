import os
import sys
import streamlit.web.cli as stcli

def resolve_path(path):
    """
    取得資源檔案的絕對路徑。
    處理開發環境與 PyInstaller 打包後的路徑差異。
    """
    if getattr(sys, "frozen", False):
        basedir = sys._MEIPASS
    else:
        basedir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(basedir, path)

if __name__ == "__main__":
    # 🚨 關鍵修正：必須為 false，瀏覽器才會自動開啟！
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "false" 
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    
    app_path = resolve_path("app.py")
    
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
    ]
    
    sys.exit(stcli.main())